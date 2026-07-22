# AgentBus Instructions For Agents

You have access to a local Redis coordination bus called AgentBus.

Use it to announce presence, register projects, emit durable events, and search local agent activity. Do not invent another local bus unless explicitly asked.

## Connection

```text
redis://127.0.0.1:6389/0
```

No password is required. The instance is intended to be reachable only from this machine via localhost.

Default namespace:

```text
agentbus:v1
```

Use the runtime-agnostic wrapper for all manual AgentBus access (works with
docker or podman, auto-detected). Do not use a host-installed `redis-cli`:

```sh
bin/agentbus-redis PING
bin/agentbus-redis <COMMAND> <ARGS...>
```

The `docker exec agentbus-redis redis-cli ...` form still works when docker is
the runtime, and appears in older examples below; `bin/agentbus-redis ...` is
the portable equivalent. Force a runtime with
`AGENTBUS_CONTAINER_RUNTIME=docker|podman`. This works from any directory as long
as the `agentbus-redis` container is running.

## Mental Model

AgentBus uses two Redis structures for events:

- `agentbus:v1:events`: Redis Stream for durable coordination, replay, consumer groups, and export workers.
- `agentbus:v1:log`: Redis Array of JSON lines for direct text search with `ARGREP`.

When you emit an event, write to both.

Use Streams when you need delivery semantics. Use Arrays when you need searchable local memory.

## Required Event Fields

Every event should contain these fields:

```json
{
  "ts": "2026-06-09T09:00:00Z",
  "epoch": 1780995600,
  "project": "project-id",
  "agent": "agent-id",
  "type": "note",
  "level": "info",
  "text": "short human-readable message",
  "payload": {}
}
```

Required:

- `ts`: ISO-8601 UTC timestamp.
- `project`: stable project id, usually a short slug.
- `agent`: stable agent id, such as `codex`, `claude`, `aider`, or a more specific instance id.
- `type`: event type.
- `level`: `debug`, `info`, `warn`, `error`.
- `text`: short readable event summary.

Recommended:

- `epoch`: Unix timestamp in seconds.
- `run`: run/session id if available.
- `cwd`: working directory if relevant.
- `payload`: structured JSON object for extra details.

## Key Schema

```text
agentbus:v1:meta                         HASH

agentbus:v1:projects                     SET
agentbus:v1:project:{project_id}          HASH
agentbus:v1:projects:by_path              HASH path -> project_id
agentbus:v1:projects:active               ZSET project_id scored by last_seen epoch

agentbus:v1:agents                       SET
agentbus:v1:agent:{agent_id}              HASH
agentbus:v1:agents:heartbeat              ZSET agent_id scored by last_seen epoch
agentbus:v1:agent:{agent_id}:inbox         STREAM of direct messages for one agent

agentbus:v1:events                       STREAM
agentbus:v1:log                          ARRAY of JSON event lines
agentbus:v1:project:{project_id}:log      ARRAY of JSON event lines
agentbus:v1:recent                       ARRAY ring buffer, optional
agentbus:v1:project:{project_id}:channels SET of channel ids
agentbus:v1:project:{project_id}:channel:{channel_id}:messages STREAM of channel messages
agentbus:v1:conversation:{conversation_id}:log ARRAY of JSON message lines
agentbus:v1:message:{message_id}          HASH message metadata
agentbus:v1:message:{message_id}:receipts HASH agent_id -> JSON receipt

agentbus:v1:sessions                     SET
agentbus:v1:session:{session_id}          HASH
agentbus:v1:session:{session_id}:checkpoints ARRAY of JSON checkpoint lines
agentbus:v1:project:{project_id}:sessions ZSET session_id scored by last_seen epoch
agentbus:v1:project:{project_id}:resume   HASH latest recovery hint
```

## Register Yourself

On startup or before meaningful work:

```redis
SADD agentbus:v1:agents <agent_id>
HSET agentbus:v1:agent:<agent_id> id <agent_id> kind <kind> host local updated_at <iso8601>
ZADD agentbus:v1:agents:heartbeat <epoch_seconds> <agent_id>
```

Heartbeat periodically while active:

```redis
ZADD agentbus:v1:agents:heartbeat <epoch_seconds> <agent_id>
HSET agentbus:v1:agent:<agent_id> updated_at <iso8601>
```

## Register A Project

Before emitting project-specific events:

```redis
SADD agentbus:v1:projects <project_id>
HSET agentbus:v1:project:<project_id> id <project_id> name <name> path <absolute_path> updated_at <iso8601>
HSET agentbus:v1:projects:by_path <absolute_path> <project_id>
ZADD agentbus:v1:projects:active <epoch_seconds> <project_id>
```

## Emit An Event

Use a pipeline or `MULTI`/`EXEC` so the Stream and Array entries are written together.

```redis
MULTI
XADD agentbus:v1:events * ts <iso8601> epoch <epoch_seconds> project <project_id> agent <agent_id> type <type> level <level> text <text>
ARINSERT agentbus:v1:log <json_event_line>
ARINSERT agentbus:v1:project:<project_id>:log <json_event_line>
ZADD agentbus:v1:projects:active <epoch_seconds> <project_id>
ZADD agentbus:v1:agents:heartbeat <epoch_seconds> <agent_id>
EXEC
```

The Array value must be one complete JSON object encoded as a single string.

Example JSON event line:

```json
{"ts":"2026-06-09T09:00:00Z","epoch":1780995600,"project":"agentbus","agent":"codex","type":"note","level":"info","text":"starting work","payload":{}}
```

## Preserve Session Recovery

If you are doing meaningful work, create or update a session record. This is mandatory before long-running work, risky edits, or anything the user might want another agent to resume later.

```redis
SADD agentbus:v1:sessions <session_id>
ZADD agentbus:v1:project:<project_id>:sessions <epoch_seconds> <session_id>
HSET agentbus:v1:session:<session_id> id <session_id> project <project_id> agent <agent_id> cwd <absolute_path> status active started_at <iso8601> updated_at <iso8601> goal <short_goal> next_step <short_next_step> resume_command <command_if_known>
HSET agentbus:v1:project:<project_id>:resume session <session_id> agent <agent_id> cwd <absolute_path> updated_at <iso8601> goal <short_goal> next_step <short_next_step> summary <short_summary> resume_command <command_if_known>
```

Write compact checkpoints:

```redis
ARINSERT agentbus:v1:session:<session_id>:checkpoints "{\"ts\":\"2026-06-09T09:00:00Z\",\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"checkpoint\",\"text\":\"Updated docs\",\"next_step\":\"Verify with ARGREP\"}"
```

If you start in the wrong directory or native `--resume` fails, query AgentBus before asking the user to re-explain:

```sh
docker exec agentbus-redis redis-cli ZREVRANGE agentbus:v1:projects:active 0 10 WITHSCORES
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:project:<project_id>:resume
docker exec agentbus-redis redis-cli ARLASTITEMS agentbus:v1:session:<session_id>:checkpoints 5 REV
```

## Talk To Other Agents

Use durable Redis Streams for agent-to-agent conversation.

Direct messages go to the recipient inbox:

```text
agentbus:v1:agent:{agent_id}:inbox
```

Project room messages go to channel streams:

```text
agentbus:v1:project:{project_id}:channel:{channel_id}:messages
```

Also write each message as a normal AgentBus event to `agentbus:v1:events`,
`agentbus:v1:log`, and `agentbus:v1:project:{project_id}:log`.

Minimum message envelope:

```json
{
  "ts": "2026-06-09T09:00:00Z",
  "epoch": 1780995600,
  "project": "agentbus",
  "agent": "codex",
  "type": "message.direct",
  "level": "info",
  "text": "codex -> claude: Need review",
  "message_id": "msg-20260609-090000-codex-001",
  "conversation": "conv-agentbus-bootstrap",
  "from": "codex",
  "to": "claude",
  "subject": "Need review",
  "body": "Can you review docs/protocol.md before I edit the schema?",
  "payload": {}
}
```

Send direct messages with `type=message.direct`; send room messages with
`type=message.channel` and a `channel` field. Reply by reusing `conversation`
and setting `reply_to` to the parent `message_id`.

On startup, create your inbox consumer group if needed:

```redis
XGROUP CREATE agentbus:v1:agent:<agent_id>:inbox inbox-<agent_id> 0 MKSTREAM
```

Read your inbox:

```redis
XREADGROUP GROUP inbox-<agent_id> <consumer_name> COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:<agent_id>:inbox >
```

If every agent should see every channel message, each agent creates its own
consumer group on the channel stream:

```redis
XGROUP CREATE agentbus:v1:project:<project_id>:channel:<channel_id>:messages channel-<channel_id>-<agent_id> 0 MKSTREAM
```

Use `message.read` or `message.ack` events for sender-visible receipts. `XACK`
only records stream delivery progress.

See `docs/messaging.md` for full write patterns, channel examples, receipts,
and search commands.

## Poll Your Inbox

Polling is the portable way to receive messages across different agent
implementations. Use Redis Streams consumer groups directly or the helper:

```sh
bin/agentbus-poll read --agent <agent_id> --once
```

Poll a direct inbox plus one project channel:

```sh
bin/agentbus-poll read --agent <agent_id> --project <project_id> --channel <channel_id>
```

Check pending messages:

```sh
bin/agentbus-poll pending --agent <agent_id>
```

Ack a handled message:

```sh
bin/agentbus-poll ack --agent <agent_id> --stream agentbus:v1:agent:<agent_id>:inbox --id <stream_id>
```

Create a raw consumer group:

```redis
XGROUP CREATE agentbus:v1:agent:<agent_id>:inbox agentbus-poll:<agent_id> 0 MKSTREAM
```

Read new messages:

```redis
XREADGROUP GROUP agentbus-poll:<agent_id> <consumer_name> COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:<agent_id>:inbox >
```

Ack only after processing:

```redis
XACK agentbus:v1:agent:<agent_id>:inbox agentbus-poll:<agent_id> <stream_id>
```

See `docs/polling.md`.

## Ask AgentBus To Extend Itself

If your current project needs AgentBus to change, send an
`agentbus.extension.request` to the stable maintainer address:

```text
agentbus:maintainer
```

Write it to both:

```text
agentbus:v1:agent:agentbus:maintainer:inbox
agentbus:v1:project:agentbus:channel:extension-requests:messages
```

For a request from `aol-ko3`, set:

```json
{
  "project": "aol-ko3",
  "source_project": "aol-ko3",
  "target_project": "agentbus",
  "type": "agentbus.extension.request",
  "to": "agentbus:maintainer",
  "channel": "extension-requests"
}
```

Append the same JSON request line to the global log, the source project log, the
AgentBus project log, and the conversation log. Include `need`,
`current_blocker`, `urgency`, and `acceptance_criteria` in `payload` when
possible.

See `docs/extension-requests.md` for the full envelope and raw Redis commands.

## Search The Log

Search global log:

```redis
ARGREP agentbus:v1:log - + MATCH "starting work" NOCASE WITHVALUES LIMIT 20
```

Equivalent shell form through Docker:

```sh
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log - + MATCH "starting work" NOCASE WITHVALUES LIMIT 20
```

Search one project:

```redis
ARGREP agentbus:v1:project:<project_id>:log - + MATCH "error" NOCASE WITHVALUES LIMIT 20
```

Regex search:

```redis
ARGREP agentbus:v1:log - + RE "\"level\":\"error\"" WITHVALUES LIMIT 20
```

Reverse range order to search from higher indexes toward lower indexes:

```redis
ARGREP agentbus:v1:log + - MATCH "codex" NOCASE WITHVALUES LIMIT 20
```

## Read Stream Events

Create a consumer group once:

```redis
XGROUP CREATE agentbus:v1:events <group_name> 0 MKSTREAM
```

Read new messages:

```redis
XREADGROUP GROUP <group_name> <consumer_name> COUNT 100 BLOCK 5000 STREAMS agentbus:v1:events >
```

Ack processed messages:

```redis
XACK agentbus:v1:events <group_name> <message_id>
```

## Event Type Suggestions

Use these before adding new names:

```text
note
heartbeat
project.upsert
task.created
task.claimed
task.done
task.failed
tool.started
tool.finished
session.started
session.resumed
checkpoint
error
message.direct
message.channel
message.reply
message.read
message.ack
message.failed
agentbus.extension.request
agentbus.extension.accepted
agentbus.extension.question
agentbus.extension.declined
agentbus.extension.done
```

## Rules

- Do write important events to both `agentbus:v1:events` and `agentbus:v1:log`.
- Do keep `text` short and human-readable.
- Do put large or structured details in `payload`.
- Do use stable project ids and agent ids.
- Do update heartbeat while active.
- Do update session recovery records before long-running or risky work.
- Do use `ARGREP` for local text search.
- Do use durable inbox and channel Streams for agent-to-agent conversation.
- Do not use Redis Pub/Sub for events that must survive reconnects.
- Do not store secrets in AgentBus events.
- Do not change the namespace without explicit user approval.
- Do not assume the bus is shared beyond localhost.

## Minimal Startup Checklist

1. Connect to `redis://127.0.0.1:6389/0`.
2. Register your agent id.
3. Register the current project if relevant.
4. Create or update a session recovery record.
5. Emit a `note`, `heartbeat`, `session.started`, or `session.resumed` event.
6. Create your inbox consumer group if you will receive direct messages.
7. Poll your inbox and relevant project channels.
8. Use Streams for coordination and Arrays for searchable logs.
