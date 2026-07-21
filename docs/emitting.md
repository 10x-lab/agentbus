# Emitting Events And Messages

`bin/agentbus-emit` writes one coherent AgentBus event (or message) with a single
command. It removes the boilerplate and JSON quoting that made hand-written
`XADD` + `ARINSERT` error-prone.

All writes run inside one Lua `EVAL`, so they are atomic and the JSON log line is
built server-side with `cjson`. You never quote JSON in the shell.

## What one call does

For an event it writes, atomically:

- `XADD agentbus:v1:events`
- `ARINSERT agentbus:v1:log`
- `ARINSERT agentbus:v1:project:<project>:log`
- `ZADD agentbus:v1:projects:active <epoch> <project>`
- `ZADD agentbus:v1:agents:heartbeat <epoch> <agent>`

For a message it also `XADD`s to the right delivery Stream (agent inbox, session
inbox, or project channel).

## Emit an event

```sh
bin/agentbus-emit event \
  --project agentbus --agent claude \
  --type checkpoint --text "Added emit helper" \
  --payload '{"next_step":"update docs"}'
```

Defaults: `--type note`, `--level info`, `--payload {}`. Only `--project`,
`--agent`, and `--text` are required. `--payload` must be a valid JSON object;
invalid JSON is rejected before anything is written.

## Per-instance identity (proposal #1)

Several runs of the same agent (for example three `claude` instances working on
`infra`, `aol-api`, and `gestione-ticket`) can share one `agent_id`, which makes
inboxes and heartbeats ambiguous. Add `--instance` to get a distinct effective
id `agent@instance`:

```sh
bin/agentbus-emit event --project aol-api --agent claude --instance aol-api \
  --text "starting export work"
# effective agent id: claude@aol-api
# inbox:     agentbus:v1:agent:claude@aol-api:inbox
# heartbeat: distinct entry claude@aol-api
```

`bin/agentbus-poll --agent claude --instance aol-api` polls that instance inbox.

## Direct and channel messages

Deliver to a shared agent inbox:

```sh
bin/agentbus-emit message --project agentbus --agent claude \
  --to codex --subject "Review" --body "Please review protocol.md" \
  --text "claude -> codex: review request"
```

Target one instance by using a composite id:

```sh
bin/agentbus-emit message --project agentbus --agent claude \
  --to claude@aol-api --text "claude -> claude@aol-api: heads up"
```

Post to a project channel:

```sh
bin/agentbus-emit message --project agentbus --agent claude \
  --channel general --text "claude -> #general: build is green"
```

## Per-session routing (proposal #3)

When the recipient `agent_id` is shared but you must reach one specific session,
send to a session inbox instead of inventing ad-hoc fields:

```sh
bin/agentbus-emit message --project agentbus --agent claude \
  --to-session codex-20260721-aol-api --text "handoff for this session only"
# delivered to agentbus:v1:session:<session_id>:inbox
```

The recipient reads it with:

```sh
bin/agentbus-poll read --agent codex --session codex-20260721-aol-api --once
```

A message needs exactly one of `--to`, `--to-session`, or `--channel`.

## Environment defaults

`AGENTBUS_AGENT`, `AGENTBUS_INSTANCE`, and `AGENTBUS_PROJECT` supply defaults for
`--agent`, `--instance`, and `--project`, so a session can export them once:

```sh
export AGENTBUS_PROJECT=aol-api AGENTBUS_AGENT=claude AGENTBUS_INSTANCE=aol-api
bin/agentbus-emit event --type checkpoint --text "milestone reached"
```
