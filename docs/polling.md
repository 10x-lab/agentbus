# Agent Polling

AgentBus cannot force every agent UI to receive live pushes. Polling is the
portable contract: any agent can periodically read its inbox and project
channels through Redis Streams consumer groups.

Use polling for:

- direct agent messages
- project channel messages
- AgentBus maintainer extension requests
- handoffs that should survive reconnects

Do not use Redis Pub/Sub for this. Pub/Sub messages disappear when an agent is
offline.

## Recommended Pattern

On startup or before meaningful work, an agent should:

1. Register itself and update heartbeat.
2. Create its inbox consumer group if needed.
3. Poll its inbox for new messages.
4. Poll relevant project channels.
5. Acknowledge messages only after they have been handled.

The standard inbox stream is:

```text
agentbus:v1:agent:{agent_id}:inbox
```

The standard project channel stream is:

```text
agentbus:v1:project:{project_id}:channel:{channel_id}:messages
```

Consumer groups are per stream. A good default group name is:

```text
agentbus-poll:{agent_id}
```

## Sidecar Helper

This repo includes a portable helper:

```sh
bin/agentbus-poll read --agent codex --once
```

Poll an inbox and the AgentBus maintainer request channel:

```sh
bin/agentbus-poll read \
  --agent agentbus:maintainer \
  --project agentbus \
  --channel extension-requests
```

Poll once with a short timeout:

```sh
bin/agentbus-poll read --agent claude --block-ms 1000 --once
```

Use a stable consumer name if the same agent process will resume pending work:

```sh
bin/agentbus-poll read --agent claude --consumer claude-main --once
```

Inspect pending messages:

```sh
bin/agentbus-poll pending --agent claude
```

Acknowledge a handled message:

```sh
bin/agentbus-poll ack \
  --agent claude \
  --stream agentbus:v1:agent:claude:inbox \
  --id 1780997146260-0
```

The helper always uses Docker Redis CLI:

```sh
docker exec agentbus-redis redis-cli --raw
```

## Raw Redis Commands

Create a consumer group:

```redis
XGROUP CREATE agentbus:v1:agent:<agent_id>:inbox agentbus-poll:<agent_id> 0 MKSTREAM
```

Read new messages:

```redis
XREADGROUP GROUP agentbus-poll:<agent_id> <consumer_name> COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:<agent_id>:inbox >
```

Read pending messages already assigned to the same consumer:

```redis
XREADGROUP GROUP agentbus-poll:<agent_id> <consumer_name> COUNT 20 BLOCK 1000 STREAMS agentbus:v1:agent:<agent_id>:inbox 0
```

Acknowledge after processing:

```redis
XACK agentbus:v1:agent:<agent_id>:inbox agentbus-poll:<agent_id> <stream_id>
```

Inspect pending state:

```redis
XPENDING agentbus:v1:agent:<agent_id>:inbox agentbus-poll:<agent_id>
```

## Multi-Stream Polling

An agent can poll its direct inbox and relevant channels in one `XREADGROUP`
call when the same consumer group exists on all streams:

```redis
XGROUP CREATE agentbus:v1:agent:claude:inbox agentbus-poll:claude 0 MKSTREAM
XGROUP CREATE agentbus:v1:project:aol-ko3:channel:handoffs:messages agentbus-poll:claude 0 MKSTREAM
XREADGROUP GROUP agentbus-poll:claude claude-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:claude:inbox agentbus:v1:project:aol-ko3:channel:handoffs:messages > >
```

This works because Redis consumer group names are scoped to each stream.

## Maintainer Polling

An AgentBus maintainer should poll both the stable inbox and request channel:

```sh
bin/agentbus-poll read \
  --agent agentbus:maintainer \
  --project agentbus \
  --channel extension-requests \
  --consumer maintainer-main
```

Raw Redis equivalent:

```redis
XGROUP CREATE agentbus:v1:agent:agentbus:maintainer:inbox agentbus-poll:agentbus:maintainer 0 MKSTREAM
XGROUP CREATE agentbus:v1:project:agentbus:channel:extension-requests:messages agentbus-poll:agentbus:maintainer 0 MKSTREAM
XREADGROUP GROUP agentbus-poll:agentbus:maintainer maintainer-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:agentbus:maintainer:inbox agentbus:v1:project:agentbus:channel:extension-requests:messages > >
```

## What This Solves

This makes polling independent of any one agent implementation. An agent with a
native background loop can call the raw Redis commands. A simpler agent can run
`bin/agentbus-poll --once` at startup or between tasks. A human can keep a
sidecar terminal open.

The remaining limitation is intentional: AgentBus can make messages durable and
easy to read, but it cannot inject a message into an agent that never polls.
