# AgentBus — Agent Setup Runbook

You are an AI coding agent. A human asked you to set up AgentBus by reading this
file. Execute the steps below top to bottom. Everything is idempotent: if a step
is already satisfied, note it and continue. Do not ask the human for anything you
can determine yourself. Only stop if a step fails and you cannot recover.

At the end you must report: whether AgentBus is running, the Redis version, and
whether the native Array commands (`ARGREP`) are available.

---

## What AgentBus is

A local Redis coordination and continuity bus for coding agents on one machine.
It runs Redis in Docker on `127.0.0.1:6389` and gives agents durable events,
searchable logs, session recovery, and agent-to-agent messaging.

It requires **Redis >= 8.8**, because it uses the native Array data type and the
`ARGREP` search command introduced in that release. The pinned image
`redis:8.8.0-alpine` (built with modules) provides these.

---

## Step 0 — Check prerequisites

```sh
docker version
docker compose version
```

If Docker is not installed or the daemon is not running, stop and tell the human
to start Docker Desktop (or install Docker). This is the only hard external
dependency you cannot install silently.

## Step 1 — Get the repository

If you are already inside the AgentBus repo (a `docker-compose.yml` with
`container_name: agentbus-redis` exists in the current directory), skip to Step 2.

Otherwise clone it next to the human's other projects:

```sh
git clone https://github.com/10x-lab/agentbus.git
cd agentbus
```

If the directory already exists, `cd` into it and `git pull` instead.

## Step 2 — Configure the environment

```sh
[ -f .env ] || cp .env.example .env
```

Defaults are fine (localhost port `6389`, namespace `agentbus:v1`). Do not change
`AGENTBUS_REDIS_BIND` from `127.0.0.1` — binding to `0.0.0.0` exposes an
unauthenticated Redis to the network.

## Step 3 — Start Redis

```sh
docker compose up -d
```

Wait for it to become healthy, then confirm:

```sh
docker exec agentbus-redis redis-cli PING
```

Expected: `PONG`. If the container was already running, this still returns
`PONG` — that is success, not an error.

## Step 4 — Verify the Redis 8.8 requirement

```sh
docker exec agentbus-redis redis-cli INFO server | grep redis_version
docker exec agentbus-redis redis-cli COMMAND INFO ARGREP
```

`redis_version` must be `8.8.0` or higher, and `COMMAND INFO ARGREP` must return
a command (not an empty reply). If `ARGREP` is empty, the wrong Redis image is
running: `docker compose down`, ensure `AGENTBUS_REDIS_IMAGE=redis:8.8.0-alpine`
in `.env`, then repeat Step 3. Do not proceed without `ARGREP`; the searchable
log depends on it.

## Step 5 — Initialize the bus

```sh
make init
```

If `make` is unavailable, run the two commands it wraps:

```sh
docker exec agentbus-redis redis-cli HSET agentbus:v1:meta version 1 redis_image redis:8.8.0-alpine
docker exec agentbus-redis redis-cli XGROUP CREATE agentbus:v1:events export-jsonl 0 MKSTREAM
```

`BUSYGROUP` from the second command means the group already exists — that is fine.

## Step 6 — Register yourself and emit a first event

Pick a stable `agent_id` for yourself (e.g. `claude`, `codex`) and a
`project_id` for the human's current project (a short slug). Use the real
current UTC timestamp and epoch.

```sh
docker exec agentbus-redis redis-cli SADD agentbus:v1:agents <agent_id>
docker exec agentbus-redis redis-cli HSET agentbus:v1:agent:<agent_id> id <agent_id> kind coding-agent host local updated_at <iso8601>
docker exec agentbus-redis redis-cli ZADD agentbus:v1:agents:heartbeat <epoch> <agent_id>

docker exec agentbus-redis redis-cli XADD agentbus:v1:events '*' ts <iso8601> epoch <epoch> project <project_id> agent <agent_id> type session.started level info text "AgentBus setup complete"
docker exec agentbus-redis redis-cli ARINSERT agentbus:v1:log '{"ts":"<iso8601>","epoch":<epoch>,"project":"<project_id>","agent":"<agent_id>","type":"session.started","level":"info","text":"AgentBus setup complete","payload":{}}'
```

## Step 7 — Confirm it all works

```sh
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:log - + MATCH "setup complete" NOCASE WITHVALUES LIMIT 5
```

You should see the event you just wrote. AgentBus is now live.

---

## Step 8 — Learn the full contract

Now read these files so you can use AgentBus for real work, not just setup:

- `AGENTBUS_FOR_AGENTS.md` — full agent contract: events, registration, messaging.
- `docs/recovery.md` — session recovery for broken terminals and failed resume.
- `docs/messaging.md` — agent-to-agent direct messages and project channels.
- `docs/polling.md` — how to poll your inbox with `bin/agentbus-poll`.

From now on, when you do meaningful work: register a session, emit events to both
the Stream and the Array log, and leave recovery checkpoints before risky or
long-running operations.

---

## Report back to the human

Tell them, in one short block:

1. AgentBus running? (PING result)
2. Redis version and whether `ARGREP` is available.
3. Your registered `agent_id` and the `project_id` you used.
4. One-line reminder that `docs/recovery.md` lets a future agent resume this work
   from any directory.
