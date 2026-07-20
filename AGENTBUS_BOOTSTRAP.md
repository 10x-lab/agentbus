# AgentBus Bootstrap

AgentBus is the local continuity and coordination bus for coding agents on this machine.

Before asking the user to restate lost context, check AgentBus.

Canonical docs:

- `AGENTBUS_FOR_AGENTS.md`
- `docs/recovery.md`

Use Redis through Docker:

```sh
docker exec agentbus-redis redis-cli PING
docker exec agentbus-redis redis-cli ZREVRANGE agentbus:v1:projects:active 0 10 WITHSCORES
docker exec agentbus-redis redis-cli HGETALL agentbus:v1:project:<project_id>:resume
```

When doing meaningful work, register or update an AgentBus session and leave checkpoints.

If AgentBus is unavailable, continue normally and mention it briefly.
