# Direct Redis Protocol

These examples show raw Redis commands.

For all manual checks, use the CLI inside the running Docker container. Do not
use a host-installed `redis-cli` for AgentBus operations:

```sh
docker exec agentbus-redis redis-cli PING
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log - + MATCH "agentbus" NOCASE WITHVALUES LIMIT 20
```

## Register A Project

```redis
SADD agentbus:v1:projects my-project
HSET agentbus:v1:project:my-project id my-project name "My Project" path "/path/to/code/my-project" created_at "2026-06-09T09:00:00Z" updated_at "2026-06-09T09:00:00Z"
HSET agentbus:v1:projects:by_path "/path/to/code/my-project" my-project
ZADD agentbus:v1:projects:active 1780995600 my-project
```

## Register Or Heartbeat An Agent

```redis
SADD agentbus:v1:agents codex
HSET agentbus:v1:agent:codex id codex kind coding host local updated_at "2026-06-09T09:00:00Z"
ZADD agentbus:v1:agents:heartbeat 1780995600 codex
```

## Emit One Event

In real clients, use `MULTI`/`EXEC` or a pipeline.

```redis
MULTI
XADD agentbus:v1:events * ts "2026-06-09T09:00:00Z" epoch 1780995600 project "my-project" agent "codex" type "note" level "info" text "starting work"
ARINSERT agentbus:v1:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"my-project\",\"agent\":\"codex\",\"type\":\"note\",\"level\":\"info\",\"text\":\"starting work\"}"
ARINSERT agentbus:v1:project:my-project:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"my-project\",\"agent\":\"codex\",\"type\":\"note\",\"level\":\"info\",\"text\":\"starting work\"}"
ZADD agentbus:v1:projects:active 1780995600 my-project
ZADD agentbus:v1:agents:heartbeat 1780995600 codex
EXEC
```

## Search

```redis
ARGREP agentbus:v1:log - + MATCH "starting" NOCASE WITHVALUES LIMIT 20
ARGREP agentbus:v1:project:my-project:log - + RE "\"level\":\"error\"" WITHVALUES LIMIT 20
ARGREP agentbus:v1:log + - MATCH "codex" NOCASE WITHVALUES LIMIT 20
```

Reverse `start` and `end` (`+ -`) to walk newest-ish indexes first when using sequential inserts.

## Agent-To-Agent Messages

Use direct inbox streams for one recipient and channel streams for shared rooms.
Also write every message to the normal AgentBus event stream and Array logs.

### Send A Direct Message

```redis
MULTI
HSET agentbus:v1:message:msg-20260609-090000-codex-001 id msg-20260609-090000-codex-001 project agentbus from codex to claude conversation conv-agentbus-bootstrap status sent created_at "2026-06-09T09:00:00Z" updated_at "2026-06-09T09:00:00Z"
XADD agentbus:v1:agent:claude:inbox * ts "2026-06-09T09:00:00Z" epoch 1780995600 project agentbus agent codex type message.direct level info text "codex -> claude: Need review" message_id msg-20260609-090000-codex-001 conversation conv-agentbus-bootstrap from codex to claude subject "Need review" body "Can you review docs/protocol.md before I edit the schema?" payload "{}"
XADD agentbus:v1:events * ts "2026-06-09T09:00:00Z" epoch 1780995600 project agentbus agent codex type message.direct level info text "codex -> claude: Need review" message_id msg-20260609-090000-codex-001 conversation conv-agentbus-bootstrap from codex to claude
ARINSERT agentbus:v1:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"message.direct\",\"level\":\"info\",\"text\":\"codex -> claude: Need review\",\"message_id\":\"msg-20260609-090000-codex-001\",\"conversation\":\"conv-agentbus-bootstrap\",\"from\":\"codex\",\"to\":\"claude\",\"subject\":\"Need review\",\"body\":\"Can you review docs/protocol.md before I edit the schema?\",\"payload\":{}}"
ARINSERT agentbus:v1:project:agentbus:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"message.direct\",\"level\":\"info\",\"text\":\"codex -> claude: Need review\",\"message_id\":\"msg-20260609-090000-codex-001\",\"conversation\":\"conv-agentbus-bootstrap\",\"from\":\"codex\",\"to\":\"claude\",\"subject\":\"Need review\",\"body\":\"Can you review docs/protocol.md before I edit the schema?\",\"payload\":{}}"
ARINSERT agentbus:v1:conversation:conv-agentbus-bootstrap:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"message.direct\",\"level\":\"info\",\"text\":\"codex -> claude: Need review\",\"message_id\":\"msg-20260609-090000-codex-001\",\"conversation\":\"conv-agentbus-bootstrap\",\"from\":\"codex\",\"to\":\"claude\",\"subject\":\"Need review\",\"body\":\"Can you review docs/protocol.md before I edit the schema?\",\"payload\":{}}"
ZADD agentbus:v1:projects:active 1780995600 agentbus
ZADD agentbus:v1:agents:heartbeat 1780995600 codex
EXEC
```

### Read Your Inbox

Create the inbox consumer group once:

```redis
XGROUP CREATE agentbus:v1:agent:claude:inbox inbox-claude 0 MKSTREAM
```

Read messages:

```redis
XREADGROUP GROUP inbox-claude claude-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:claude:inbox >
```

After processing:

```redis
XACK agentbus:v1:agent:claude:inbox inbox-claude <stream_id>
```

### Send A Channel Message

```redis
MULTI
SADD agentbus:v1:project:agentbus:channels general
XADD agentbus:v1:project:agentbus:channel:general:messages * ts "2026-06-09T09:00:00Z" epoch 1780995600 project agentbus agent codex type message.channel level info text "codex in #general: Status" message_id msg-20260609-090000-codex-002 conversation conv-agentbus-general from codex channel general subject "Status" body "I am updating the messaging docs." payload "{}"
XADD agentbus:v1:events * ts "2026-06-09T09:00:00Z" epoch 1780995600 project agentbus agent codex type message.channel level info text "codex in #general: Status" message_id msg-20260609-090000-codex-002 conversation conv-agentbus-general from codex channel general
ARINSERT agentbus:v1:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"message.channel\",\"level\":\"info\",\"text\":\"codex in #general: Status\",\"message_id\":\"msg-20260609-090000-codex-002\",\"conversation\":\"conv-agentbus-general\",\"from\":\"codex\",\"channel\":\"general\",\"subject\":\"Status\",\"body\":\"I am updating the messaging docs.\",\"payload\":{}}"
ARINSERT agentbus:v1:project:agentbus:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"message.channel\",\"level\":\"info\",\"text\":\"codex in #general: Status\",\"message_id\":\"msg-20260609-090000-codex-002\",\"conversation\":\"conv-agentbus-general\",\"from\":\"codex\",\"channel\":\"general\",\"subject\":\"Status\",\"body\":\"I am updating the messaging docs.\",\"payload\":{}}"
ARINSERT agentbus:v1:conversation:conv-agentbus-general:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"message.channel\",\"level\":\"info\",\"text\":\"codex in #general: Status\",\"message_id\":\"msg-20260609-090000-codex-002\",\"conversation\":\"conv-agentbus-general\",\"from\":\"codex\",\"channel\":\"general\",\"subject\":\"Status\",\"body\":\"I am updating the messaging docs.\",\"payload\":{}}"
ZADD agentbus:v1:projects:active 1780995600 agentbus
ZADD agentbus:v1:agents:heartbeat 1780995600 codex
EXEC
```

Every agent that should see all channel messages creates its own consumer group:

```redis
XGROUP CREATE agentbus:v1:project:agentbus:channel:general:messages channel-general-claude 0 MKSTREAM
XREADGROUP GROUP channel-general-claude claude-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:project:agentbus:channel:general:messages >
```

See `docs/messaging.md` for replies, receipts, and search.

## Poll For Messages

The portable polling helper wraps Redis Streams consumer groups:

```sh
bin/agentbus-poll read --agent claude --once
bin/agentbus-poll read --agent claude --project aol-ko3 --channel handoffs
bin/agentbus-poll pending --agent claude
```

Raw Redis equivalent:

```redis
XGROUP CREATE agentbus:v1:agent:claude:inbox agentbus-poll:claude 0 MKSTREAM
XREADGROUP GROUP agentbus-poll:claude claude-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:claude:inbox >
XACK agentbus:v1:agent:claude:inbox agentbus-poll:claude <stream_id>
```

Poll an inbox and a channel in one call by creating the same group on both
streams:

```redis
XGROUP CREATE agentbus:v1:project:aol-ko3:channel:handoffs:messages agentbus-poll:claude 0 MKSTREAM
XREADGROUP GROUP agentbus-poll:claude claude-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:claude:inbox agentbus:v1:project:aol-ko3:channel:handoffs:messages > >
```

See `docs/polling.md`.

## Ask AgentBus To Extend Itself

When an agent in another project needs AgentBus to change, send an
`agentbus.extension.request` to the stable maintainer address:

```text
agentbus:maintainer
```

Keep `project` as the source project and set `target_project=agentbus`.

Example from `aol-ko3`:

```redis
MULTI
SADD agentbus:v1:project:agentbus:channels extension-requests
HSET agentbus:v1:request:req-20260609-aol-ko3-agentbus-routing id req-20260609-aol-ko3-agentbus-routing source_project aol-ko3 target_project agentbus from claude to agentbus:maintainer status open created_at "2026-06-09T09:00:00Z" updated_at "2026-06-09T09:00:00Z" conversation conv-aol-ko3-agentbus-routing
XADD agentbus:v1:agent:agentbus:maintainer:inbox * ts "2026-06-09T09:00:00Z" epoch 1780995600 project aol-ko3 source_project aol-ko3 target_project agentbus agent claude type agentbus.extension.request level info text "aol-ko3 -> agentbus:maintainer: Need scoped request routing" message_id msg-20260609-090000-claude-agentbus-001 request_id req-20260609-aol-ko3-agentbus-routing conversation conv-aol-ko3-agentbus-routing from claude to agentbus:maintainer channel extension-requests subject "Need scoped request routing" body "aol-ko3 needs a way to ask AgentBus for a protocol extension without losing the request in local project logs." payload "{\"need\":\"Route extension requests to an AgentBus maintainer inbox.\",\"urgency\":\"normal\"}"
XADD agentbus:v1:project:agentbus:channel:extension-requests:messages * ts "2026-06-09T09:00:00Z" epoch 1780995600 project aol-ko3 source_project aol-ko3 target_project agentbus agent claude type agentbus.extension.request level info text "aol-ko3 -> agentbus:maintainer: Need scoped request routing" message_id msg-20260609-090000-claude-agentbus-001 request_id req-20260609-aol-ko3-agentbus-routing conversation conv-aol-ko3-agentbus-routing from claude to agentbus:maintainer channel extension-requests subject "Need scoped request routing" body "aol-ko3 needs a way to ask AgentBus for a protocol extension without losing the request in local project logs." payload "{\"need\":\"Route extension requests to an AgentBus maintainer inbox.\",\"urgency\":\"normal\"}"
XADD agentbus:v1:events * ts "2026-06-09T09:00:00Z" epoch 1780995600 project aol-ko3 source_project aol-ko3 target_project agentbus agent claude type agentbus.extension.request level info text "aol-ko3 -> agentbus:maintainer: Need scoped request routing" message_id msg-20260609-090000-claude-agentbus-001 request_id req-20260609-aol-ko3-agentbus-routing conversation conv-aol-ko3-agentbus-routing from claude to agentbus:maintainer
ARINSERT agentbus:v1:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"aol-ko3\",\"source_project\":\"aol-ko3\",\"target_project\":\"agentbus\",\"agent\":\"claude\",\"type\":\"agentbus.extension.request\",\"level\":\"info\",\"text\":\"aol-ko3 -> agentbus:maintainer: Need scoped request routing\",\"message_id\":\"msg-20260609-090000-claude-agentbus-001\",\"request_id\":\"req-20260609-aol-ko3-agentbus-routing\",\"conversation\":\"conv-aol-ko3-agentbus-routing\",\"from\":\"claude\",\"to\":\"agentbus:maintainer\",\"channel\":\"extension-requests\",\"subject\":\"Need scoped request routing\",\"body\":\"aol-ko3 needs a way to ask AgentBus for a protocol extension without losing the request in local project logs.\",\"payload\":{\"need\":\"Route extension requests to an AgentBus maintainer inbox.\",\"urgency\":\"normal\"}}"
ARINSERT agentbus:v1:project:aol-ko3:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"aol-ko3\",\"source_project\":\"aol-ko3\",\"target_project\":\"agentbus\",\"agent\":\"claude\",\"type\":\"agentbus.extension.request\",\"level\":\"info\",\"text\":\"aol-ko3 -> agentbus:maintainer: Need scoped request routing\",\"message_id\":\"msg-20260609-090000-claude-agentbus-001\",\"request_id\":\"req-20260609-aol-ko3-agentbus-routing\",\"conversation\":\"conv-aol-ko3-agentbus-routing\",\"from\":\"claude\",\"to\":\"agentbus:maintainer\",\"channel\":\"extension-requests\",\"subject\":\"Need scoped request routing\",\"body\":\"aol-ko3 needs a way to ask AgentBus for a protocol extension without losing the request in local project logs.\",\"payload\":{\"need\":\"Route extension requests to an AgentBus maintainer inbox.\",\"urgency\":\"normal\"}}"
ARINSERT agentbus:v1:project:agentbus:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"aol-ko3\",\"source_project\":\"aol-ko3\",\"target_project\":\"agentbus\",\"agent\":\"claude\",\"type\":\"agentbus.extension.request\",\"level\":\"info\",\"text\":\"aol-ko3 -> agentbus:maintainer: Need scoped request routing\",\"message_id\":\"msg-20260609-090000-claude-agentbus-001\",\"request_id\":\"req-20260609-aol-ko3-agentbus-routing\",\"conversation\":\"conv-aol-ko3-agentbus-routing\",\"from\":\"claude\",\"to\":\"agentbus:maintainer\",\"channel\":\"extension-requests\",\"subject\":\"Need scoped request routing\",\"body\":\"aol-ko3 needs a way to ask AgentBus for a protocol extension without losing the request in local project logs.\",\"payload\":{\"need\":\"Route extension requests to an AgentBus maintainer inbox.\",\"urgency\":\"normal\"}}"
ARINSERT agentbus:v1:conversation:conv-aol-ko3-agentbus-routing:log "{\"ts\":\"2026-06-09T09:00:00Z\",\"epoch\":1780995600,\"project\":\"aol-ko3\",\"source_project\":\"aol-ko3\",\"target_project\":\"agentbus\",\"agent\":\"claude\",\"type\":\"agentbus.extension.request\",\"level\":\"info\",\"text\":\"aol-ko3 -> agentbus:maintainer: Need scoped request routing\",\"message_id\":\"msg-20260609-090000-claude-agentbus-001\",\"request_id\":\"req-20260609-aol-ko3-agentbus-routing\",\"conversation\":\"conv-aol-ko3-agentbus-routing\",\"from\":\"claude\",\"to\":\"agentbus:maintainer\",\"channel\":\"extension-requests\",\"subject\":\"Need scoped request routing\",\"body\":\"aol-ko3 needs a way to ask AgentBus for a protocol extension without losing the request in local project logs.\",\"payload\":{\"need\":\"Route extension requests to an AgentBus maintainer inbox.\",\"urgency\":\"normal\"}}"
ZADD agentbus:v1:projects:active 1780995600 aol-ko3
ZADD agentbus:v1:projects:active 1780995600 agentbus
ZADD agentbus:v1:agents:heartbeat 1780995600 claude
EXEC
```

See `docs/extension-requests.md` for maintainer startup, statuses, replies, and
search.

## Session Recovery

Use this when a terminal dies, native `--resume` fails, or a new shell starts in the wrong directory.

```redis
SADD agentbus:v1:sessions <session_id>
ZADD agentbus:v1:project:<project_id>:sessions <epoch_seconds> <session_id>
HSET agentbus:v1:session:<session_id> id <session_id> project <project_id> agent <agent_id> cwd <absolute_path> status active started_at <iso8601> updated_at <iso8601> goal <short_goal> next_step <short_next_step> resume_command <command_if_known>
HSET agentbus:v1:project:<project_id>:resume session <session_id> agent <agent_id> cwd <absolute_path> updated_at <iso8601> goal <short_goal> next_step <short_next_step> summary <short_summary> resume_command <command_if_known>
ARINSERT agentbus:v1:session:<session_id>:checkpoints <json_checkpoint_line>
```

Recover from any directory:

```sh
docker exec agentbus-redis redis-cli ZREVRANGE agentbus:v1:projects:active 0 10 WITHSCORES
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:project:<project_id>:resume
docker exec agentbus-redis redis-cli ARLASTITEMS agentbus:v1:session:<session_id>:checkpoints 5 REV
```

## Recent Window

For a bounded recent buffer:

```redis
ARRING agentbus:v1:recent 100000 "{\"ts\":\"2026-06-09T09:00:00Z\",\"project\":\"my-project\",\"agent\":\"codex\",\"type\":\"note\",\"level\":\"info\",\"text\":\"recent only\"}"
ARLASTITEMS agentbus:v1:recent 20 REV
ARGREP agentbus:v1:recent - + MATCH "recent" NOCASE WITHVALUES LIMIT 20
```

## Stream Consumers

Create a group:

```redis
XGROUP CREATE agentbus:v1:events export-jsonl 0 MKSTREAM
```

Read new work:

```redis
XREADGROUP GROUP export-jsonl worker-1 COUNT 100 BLOCK 5000 STREAMS agentbus:v1:events >
```

Ack after export:

```redis
XACK agentbus:v1:events export-jsonl <message-id>
```
