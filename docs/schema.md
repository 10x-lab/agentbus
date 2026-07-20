# AgentBus Redis Schema

Default namespace: `agentbus:v1`.

## Core Keys

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
agentbus:v1:request:{request_id}          HASH request metadata

agentbus:v1:sessions                     SET
agentbus:v1:session:{session_id}          HASH
agentbus:v1:session:{session_id}:checkpoints ARRAY of JSON checkpoint lines
agentbus:v1:project:{project_id}:sessions ZSET session_id scored by last_seen epoch
agentbus:v1:project:{project_id}:resume   HASH latest recovery hint
```

## Event Fields

Use the same field names in Stream entries and Array JSON lines.

```json
{
  "ts": "2026-06-09T09:00:00Z",
  "epoch": 1780995600,
  "project": "agentbus",
  "agent": "codex",
  "run": "optional-run-id",
  "type": "note",
  "level": "info",
  "text": "AgentBus online",
  "cwd": "/path/to/agentbus",
  "payload": {}
}
```

Required:

- `ts`
- `project`
- `agent`
- `type`
- `level`
- `text`

Recommended:

- `epoch`
- `cwd`
- `run`
- `payload`

## Well-Known Agents

Some agent ids are stable service addresses rather than one concrete run:

```text
agentbus:maintainer
```

Use `agentbus:maintainer` for requests to extend or repair AgentBus itself. A
concrete maintainer session can register this id and record its transient run in
`agentbus:v1:agent:agentbus:maintainer`.

## Message Fields

Agent-to-agent messages use the normal event fields plus message metadata.

```json
{
  "ts": "2026-06-09T09:00:00Z",
  "epoch": 1780995600,
  "project": "agentbus",
  "agent": "codex",
  "run": "optional-run-id",
  "cwd": "/path/to/agentbus",
  "type": "message.direct",
  "level": "info",
  "text": "codex -> claude: Need review",
  "message_id": "msg-20260609-090000-codex-001",
  "conversation": "conv-agentbus-bootstrap",
  "from": "codex",
  "to": "claude",
  "channel": null,
  "reply_to": null,
  "subject": "Need review",
  "body": "Can you review docs/protocol.md before I edit the schema?",
  "payload": {}
}
```

For direct messages, write to `agentbus:v1:agent:{to}:inbox` and set
`type=message.direct`. For shared project channels, write to
`agentbus:v1:project:{project_id}:channel:{channel_id}:messages`, set
`type=message.channel`, and set `channel` to the channel id.

`message_id` is sender-generated before writing. Redis Stream ids are delivery
ids, not logical message ids.

## Cross-Project Request Fields

When a message asks one project to change something for another project, keep
`project` as the source project and add explicit routing fields.

For example, an agent in `aol-ko3` asking AgentBus for an extension should use:

```json
{
  "project": "aol-ko3",
  "source_project": "aol-ko3",
  "target_project": "agentbus",
  "type": "agentbus.extension.request",
  "to": "agentbus:maintainer",
  "channel": "extension-requests",
  "request_id": "req-20260609-aol-ko3-agentbus-routing"
}
```

Append cross-project request JSON lines to the global log, the source project
log, the target project log, and the conversation log. Store request status in
`agentbus:v1:request:{request_id}`.

## Event Types

Start with a small vocabulary. Add more only when a consumer needs them.

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

## Log Strategy

Use `agentbus:v1:events` for durable event delivery and replay. Use `agentbus:v1:log` for searchable local memory.

Arrays are especially useful for:

- `ARGREP ... MATCH`
- `ARGREP ... GLOB`
- `ARGREP ... RE`
- `ARLASTITEMS` for recent lines
- `ARRING` for fixed-size recent windows

Streams are especially useful for:

- consumer groups
- ack/retry workflows
- chronological replay
- export daemons

## Retention

Initial default: keep everything in the AOF-backed Redis volume.

When the log grows, add one of these:

- daily JSONL export from the Stream
- `ARRING agentbus:v1:recent 100000 <json_event_line>` for bounded recent search
- cold archive in SQLite or Postgres if query needs outgrow Redis
