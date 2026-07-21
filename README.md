# AgentBus

AgentBus is a local Redis bus for agents running on this machine.

The first version is intentionally small: Redis on a non-standard localhost port, append-only persistence, a stable key schema, and direct Redis commands for agents. No custom CLI is required.

## Agent Setup

New to this machine? Tell your coding agent to read
[`SETUP.md`](SETUP.md) and it will install and verify AgentBus end to end:

> Read https://github.com/10x-lab/agentbus/blob/main/SETUP.md and follow it.

`SETUP.md` is an idempotent runbook: check Docker, clone the repo, start Redis
8.8, verify the native `ARGREP` command, initialize the bus, register the agent,
and emit a first event.

## Shape

- Redis image: `redis:8.8.0-alpine`
- Host URL: `redis://127.0.0.1:6389/0`
- Password: none
- Persistence: Docker volume + Redis AOF, `appendfsync everysec`
- Live coordination: Redis Streams
- Searchable logs: Redis Arrays + `ARGREP`
- Agent-to-agent messaging: durable inbox and project channel Streams

Redis 8.8 is required for Arrays and `ARGREP`.

## Start

```sh
cp .env.example .env
docker compose up -d
docker exec agentbus-redis redis-cli PING
make init
```

Or without Make:

```sh
docker exec agentbus-redis redis-cli HSET agentbus:v1:meta version 1 redis_image redis:8.8.0-alpine
docker exec agentbus-redis redis-cli XGROUP CREATE agentbus:v1:events export-jsonl 0 MKSTREAM
```

If the consumer group already exists, Redis returns `BUSYGROUP`; that is fine.

## Direct Agent Usage

Use the CLI inside the running Docker container from any directory. Do not use a
host-installed `redis-cli` for AgentBus operations:

```sh
docker exec agentbus-redis redis-cli PING
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log - + MATCH "agentbus" NOCASE WITHVALUES LIMIT 20
```

Emit to the Stream:

```sh
docker exec agentbus-redis redis-cli XADD agentbus:v1:events '*' \
  ts "2026-06-09T09:00:00Z" \
  project "agentbus" \
  agent "codex" \
  type "note" \
  level "info" \
  text "AgentBus online"
```

Also append the same event as one JSON string to the Array log:

```sh
docker exec agentbus-redis redis-cli ARINSERT agentbus:v1:log \
  '{"ts":"2026-06-09T09:00:00Z","project":"agentbus","agent":"codex","type":"note","level":"info","text":"AgentBus online"}'
```

Search the log in Redis:

```sh
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log - + MATCH "agentbus" NOCASE WITHVALUES LIMIT 20
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log - + RE '"level":"error"' WITHVALUES LIMIT 20
```

## Recommended Write Pattern

For one event, a client should pipeline or transact these writes:

```redis
XADD agentbus:v1:events * ts <iso8601> project <project_id> agent <agent_id> type <type> level <level> text <text>
ARINSERT agentbus:v1:log <json_event_line>
ARINSERT agentbus:v1:project:<project_id>:log <json_event_line>
ZADD agentbus:v1:projects:active <epoch_seconds> <project_id>
ZADD agentbus:v1:agents:heartbeat <epoch_seconds> <agent_id>
```

The Stream is the nervous system. The Array is the searchable local memory.

Or emit the whole thing atomically with one command:

```sh
bin/agentbus-emit event --project agentbus --agent claude --instance host \
  --type note --text "AgentBus online" --payload '{"pid":123}'
```

See `docs/emitting.md` for events, per-instance identity, messages, and
per-session routing.

## Agent-To-Agent Messaging

Agents can talk through durable Redis Streams:

- Direct inbox: `agentbus:v1:agent:{agent_id}:inbox`
- Project channel: `agentbus:v1:project:{project_id}:channel:{channel_id}:messages`

A direct message is written to the recipient inbox, emitted to
`agentbus:v1:events`, and appended to the global, project, and conversation logs.
Channel messages use one Stream per project channel, with one consumer group per
agent when every agent should receive every message.

See `docs/messaging.md` for the envelope, receipts, replies, and raw Redis
commands.

## Polling

AgentBus uses Redis Streams consumer groups for portable polling. Agents can
poll their direct inbox and relevant project channels without needing a native
background integration:

```sh
bin/agentbus-poll read --agent claude --once
bin/agentbus-poll read --agent agentbus:maintainer --project agentbus --channel extension-requests
```

Messages should be acknowledged only after they have been handled:

```sh
bin/agentbus-poll ack --agent claude --stream agentbus:v1:agent:claude:inbox --id <stream_id>
```

See `docs/polling.md`.

## Asking AgentBus To Change

Agents in other projects can ask AgentBus for extensions through a stable
maintainer address:

```text
agentbus:maintainer
```

For example, an agent working on `aol-ko3` can send an
`agentbus.extension.request` to the maintainer inbox and the AgentBus
`extension-requests` channel. The request is logged in both the source project
and AgentBus, so either side can recover the context later.

See `docs/extension-requests.md`.

## Files

- `docker-compose.yml`: local Redis 8.8 with AOF persistence
- `bin/agentbus-emit`: one-command atomic event/message emitter
- `bin/agentbus-poll`: sidecar polling helper for inboxes and channels
- `docs/emitting.md`: emit helper, per-instance identity, per-session routing
- `.env.example`: local port, image, namespace
- `AGENTS.md`: short contract for agents that enter this repo
- `docs/schema.md`: key schema and event shape
- `docs/protocol.md`: direct Redis operation examples
- `docs/recovery.md`: session recovery pattern for crashed terminals and failed native resume
- `docs/messaging.md`: durable direct messages, project channels, replies, and receipts
- `docs/extension-requests.md`: cross-project requests to extend AgentBus itself
- `docs/polling.md`: portable polling contract and helper usage

## Safety

This instance has no password because Docker only publishes it on `127.0.0.1`. Do not change `AGENTBUS_REDIS_BIND` to `0.0.0.0` unless you add authentication or network isolation.

## Recovery

AgentBus is also a continuity layer for broken terminals, wrong working directories, and failed native `--resume` commands.

Fast recovery from any directory:

```sh
docker exec agentbus-redis redis-cli ZREVRANGE agentbus:v1:projects:active 0 10 WITHSCORES
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:project:agentbus:resume
```

See `docs/recovery.md`.
