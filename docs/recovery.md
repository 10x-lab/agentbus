# Session Recovery

AgentBus should make it cheap to recover after a broken terminal, wrong working directory, failed `--resume`, or forgotten context.

The goal is not to store full transcripts. The goal is to leave enough breadcrumbs for a new agent invocation to know:

- which project was active
- which directory to enter
- which session/run was active
- what the user wanted
- what was already done
- what the next useful step is

## Recovery Keys

```text
agentbus:v1:sessions                          SET
agentbus:v1:session:{session_id}               HASH
agentbus:v1:session:{session_id}:checkpoints   ARRAY of JSON checkpoint lines
agentbus:v1:project:{project_id}:sessions      ZSET session_id scored by last_seen epoch
agentbus:v1:project:{project_id}:resume        HASH latest recovery hint
```

Session ids should be stable enough to identify an agent run. If the agent has a native session id, use it. Otherwise use a compact generated id such as:

```text
codex-20260609-0717-agentbus
```

## Session Hash

```redis
HSET agentbus:v1:session:<session_id> \
  id <session_id> \
  project <project_id> \
  agent <agent_id> \
  cwd <absolute_path> \
  status active \
  started_at <iso8601> \
  updated_at <iso8601> \
  resume_command <command_if_known> \
  goal <short_goal> \
  next_step <short_next_step>
```

Useful statuses:

```text
active
paused
blocked
done
abandoned
```

## Project Resume Hint

Keep one latest hint per project:

```redis
HSET agentbus:v1:project:<project_id>:resume \
  session <session_id> \
  agent <agent_id> \
  cwd <absolute_path> \
  updated_at <iso8601> \
  resume_command <command_if_known> \
  goal <short_goal> \
  next_step <short_next_step> \
  summary <short_summary>
```

This is the fast path when a human says "resume the AgentBus work" but the shell is in the wrong directory.

## Checkpoints

Write checkpoints as JSON lines to the session Array:

```redis
ARINSERT agentbus:v1:session:<session_id>:checkpoints \
  "{\"ts\":\"2026-06-09T09:00:00Z\",\"project\":\"agentbus\",\"agent\":\"codex\",\"type\":\"checkpoint\",\"text\":\"Added Redis Docker docs\",\"next_step\":\"Test ARGREP recovery search\"}"
```

Also emit a normal event to:

```text
agentbus:v1:events
agentbus:v1:log
agentbus:v1:project:{project_id}:log
```

## Startup Ritual

Every agent should do this at the beginning of meaningful work:

1. Register itself in `agentbus:v1:agents`.
2. Register the project in `agentbus:v1:projects`.
3. Create or update `agentbus:v1:session:{session_id}`.
4. Add the session id to `agentbus:v1:sessions`.
5. Add the session id to `agentbus:v1:project:{project_id}:sessions`.
6. Update `agentbus:v1:project:{project_id}:resume`.
7. Emit a `session.started` or `session.resumed` event.
8. Create or read the agent inbox if this agent receives direct messages.
9. Poll direct inboxes and relevant project channels before asking the user for context.

## Before Risky Or Long Work

Before edits, long commands, dependency installs, or anything likely to be interrupted:

```redis
ARINSERT agentbus:v1:session:<session_id>:checkpoints <json_checkpoint_line>
HSET agentbus:v1:session:<session_id> updated_at <iso8601> next_step <short_next_step>
HSET agentbus:v1:project:<project_id>:resume updated_at <iso8601> next_step <short_next_step> summary <short_summary>
```

## Recovery Commands

From any directory, using the Docker Redis CLI:

```sh
docker exec agentbus-redis redis-cli ZREVRANGE agentbus:v1:projects:active 0 10 WITHSCORES
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:project:agentbus:resume
docker exec agentbus-redis redis-cli ZREVRANGE agentbus:v1:project:agentbus:sessions 0 5 WITHSCORES
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:session:<session_id>
docker exec agentbus-redis redis-cli ARLASTITEMS agentbus:v1:session:<session_id>:checkpoints 5 REV
```

Search recovery breadcrumbs:

```sh
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log + - MATCH "checkpoint" NOCASE WITHVALUES LIMIT 20
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log + - MATCH "resume" NOCASE WITHVALUES LIMIT 20
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:project:agentbus:log + - MATCH "next_step" NOCASE WITHVALUES LIMIT 20
```

If the previous agent may have handed off work through AgentBus messaging,
inspect the active agent inbox and project channels:

```sh
docker exec agentbus-redis redis-cli XREVRANGE agentbus:v1:agent:<agent_id>:inbox + - COUNT 10
docker exec agentbus-redis redis-cli SMEMBERS agentbus:v1:project:<project_id>:channels
docker exec agentbus-redis redis-cli XREVRANGE agentbus:v1:project:<project_id>:channel:general:messages + - COUNT 10
```

Or use the portable helper:

```sh
bin/agentbus-poll read --agent <agent_id> --project <project_id> --channel general --once
bin/agentbus-poll pending --agent <agent_id>
```

## Agent Rule

If an agent starts in an unfamiliar directory or `--resume` fails, it should query AgentBus before asking the user to re-explain the work.

Minimum query:

```sh
docker exec agentbus-redis redis-cli ZREVRANGE agentbus:v1:projects:active 0 10 WITHSCORES
```

Then inspect the relevant project resume hint:

```sh
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:project:<project_id>:resume
```
