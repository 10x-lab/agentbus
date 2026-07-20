# AgentBus Local Contract

AgentBus is a local Redis coordination bus.

- Redis URL: `redis://127.0.0.1:6389/0`
- Password: none
- Namespace: `agentbus:v1`
- Durable live event bus: `agentbus:v1:events` as a Redis Stream
- Searchable text log: `agentbus:v1:log` as a Redis Array
- Project searchable log: `agentbus:v1:project:{project_id}:log` as a Redis Array
- Session recovery hint: `agentbus:v1:project:{project_id}:resume` as a Redis Hash
- Session checkpoints: `agentbus:v1:session:{session_id}:checkpoints` as a Redis Array
- Agent inbox: `agentbus:v1:agent:{agent_id}:inbox` as a Redis Stream
- Project channels: `agentbus:v1:project:{project_id}:channel:{channel_id}:messages` as Redis Streams

For manual Redis CLI access, prefer the CLI inside the Docker container:

```sh
docker exec agentbus-redis redis-cli PING
docker exec agentbus-redis redis-cli <COMMAND> <ARGS...>
```

When emitting an event, write it to both the Stream and the Array log. The Stream is for coordination, replay, and consumers. The Array is for direct in-Redis search with `ARGREP`.

When doing meaningful work, update session recovery records before risky or long-running operations:

```sh
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:project:<project_id>:resume
docker exec agentbus-redis redis-cli ARLASTITEMS agentbus:v1:session:<session_id>:checkpoints 5 REV
```

If native `--resume` fails or the shell starts in the wrong directory, query AgentBus before asking the user to re-explain the work.

Use JSON strings as Array elements. Keep top-level fields stable:

- `ts`
- `project`
- `agent`
- `type`
- `level`
- `text`
- `payload`

Do not use Redis Pub/Sub for work that must survive reconnects. Use Streams or Arrays.

For agent-to-agent conversation, use durable inbox and channel streams. Direct
messages go to `agentbus:v1:agent:{agent_id}:inbox`; shared project messages go
to `agentbus:v1:project:{project_id}:channel:{channel_id}:messages`. Also write
message events to `agentbus:v1:events`, `agentbus:v1:log`, and the project log.
See `docs/messaging.md`.

If another project needs AgentBus itself to change, send an
`agentbus.extension.request` to the stable maintainer address
`agentbus:maintainer`. Deliver it to
`agentbus:v1:agent:agentbus:maintainer:inbox` and
`agentbus:v1:project:agentbus:channel:extension-requests:messages`, and log it
in both the source project log and the AgentBus project log. See
`docs/extension-requests.md`.

For portable polling, use Redis Streams consumer groups or the helper:

```sh
bin/agentbus-poll read --agent <agent_id> --once
bin/agentbus-poll read --agent agentbus:maintainer --project agentbus --channel extension-requests
```

Poll direct inboxes and relevant project channels at startup, before asking the
user for context, and before/after long work. See `docs/polling.md`.
