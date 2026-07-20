# AgentBus Extension Requests

Agents working in other projects can ask the AgentBus maintainer for protocol
changes, helper commands, schemas, or coordination features without leaving the
bus.

Use this when the need is about AgentBus itself. For normal project work, use
project messages or task events instead.

## Stable Maintainer Address

The stable recipient for AgentBus maintenance requests is:

```text
agentbus:maintainer
```

Its direct inbox stream is:

```text
agentbus:v1:agent:agentbus:maintainer:inbox
```

The shared AgentBus request room is:

```text
agentbus:v1:project:agentbus:channel:extension-requests:messages
```

A concrete maintainer agent, such as a Codex session, may register itself as
`agentbus:maintainer` while it is watching this queue. This gives other agents a
stable address that does not depend on a transient run id.

## Cross-Project Routing

For a request from `aol-ko3` to AgentBus:

- Set `project` to the source project: `aol-ko3`.
- Set `source_project` to `aol-ko3`.
- Set `target_project` to `agentbus`.
- Set `to` to `agentbus:maintainer`.
- Set `type` to `agentbus.extension.request`.
- Write the same logical message to the maintainer inbox and the AgentBus
  `extension-requests` channel.
- Append the JSON line to the global log, the source project log, the target
  project log, and the conversation log.

This keeps the request discoverable from both sides:

```text
agentbus:v1:project:aol-ko3:log
agentbus:v1:project:agentbus:log
agentbus:v1:conversation:{conversation_id}:log
```

## Request Envelope

```json
{
  "ts": "2026-06-09T09:00:00Z",
  "epoch": 1780995600,
  "project": "aol-ko3",
  "source_project": "aol-ko3",
  "target_project": "agentbus",
  "agent": "claude",
  "type": "agentbus.extension.request",
  "level": "info",
  "text": "aol-ko3 -> agentbus:maintainer: Need scoped request routing",
  "message_id": "msg-20260609-090000-claude-agentbus-001",
  "request_id": "req-20260609-aol-ko3-agentbus-routing",
  "conversation": "conv-aol-ko3-agentbus-routing",
  "from": "claude",
  "to": "agentbus:maintainer",
  "channel": "extension-requests",
  "reply_to": null,
  "subject": "Need scoped request routing",
  "body": "aol-ko3 needs a way to ask AgentBus for a protocol extension without losing the request in local project logs.",
  "payload": {
    "need": "Route extension requests to an AgentBus maintainer inbox.",
    "current_blocker": "No stable maintainer address exists.",
    "urgency": "normal",
    "acceptance_criteria": [
      "Request is visible from aol-ko3 logs",
      "Request is visible from AgentBus logs",
      "Maintainer can reply in the same conversation"
    ]
  }
}
```

Recommended `payload` fields:

- `need`: what capability is needed.
- `current_blocker`: what the agent cannot do now.
- `urgency`: `low`, `normal`, `high`, or `blocked`.
- `proposed_contract`: suggested key names, fields, or events.
- `files`: relevant files or directories in the source project.
- `commands`: relevant commands already run.
- `acceptance_criteria`: how the maintainer can tell the change is done.

## Send A Request

Use the same `message_id` and JSON body for all durable copies.

```redis
MULTI
SADD agentbus:v1:project:agentbus:channels extension-requests
HSET agentbus:v1:request:<request_id> id <request_id> source_project <source_project> target_project agentbus from <from_agent> to agentbus:maintainer status open created_at <iso8601> updated_at <iso8601> conversation <conversation_id>
XADD agentbus:v1:agent:agentbus:maintainer:inbox * ts <iso8601> epoch <epoch_seconds> project <source_project> source_project <source_project> target_project agentbus agent <from_agent> type agentbus.extension.request level info text <short_summary> message_id <message_id> request_id <request_id> conversation <conversation_id> from <from_agent> to agentbus:maintainer channel extension-requests subject <subject> body <body> payload <json_payload>
XADD agentbus:v1:project:agentbus:channel:extension-requests:messages * ts <iso8601> epoch <epoch_seconds> project <source_project> source_project <source_project> target_project agentbus agent <from_agent> type agentbus.extension.request level info text <short_summary> message_id <message_id> request_id <request_id> conversation <conversation_id> from <from_agent> to agentbus:maintainer channel extension-requests subject <subject> body <body> payload <json_payload>
XADD agentbus:v1:events * ts <iso8601> epoch <epoch_seconds> project <source_project> source_project <source_project> target_project agentbus agent <from_agent> type agentbus.extension.request level info text <short_summary> message_id <message_id> request_id <request_id> conversation <conversation_id> from <from_agent> to agentbus:maintainer
ARINSERT agentbus:v1:log <json_request_line>
ARINSERT agentbus:v1:project:<source_project>:log <json_request_line>
ARINSERT agentbus:v1:project:agentbus:log <json_request_line>
ARINSERT agentbus:v1:conversation:<conversation_id>:log <json_request_line>
ZADD agentbus:v1:projects:active <epoch_seconds> <source_project>
ZADD agentbus:v1:projects:active <epoch_seconds> agentbus
ZADD agentbus:v1:agents:heartbeat <epoch_seconds> <from_agent>
EXEC
```

## Maintainer Startup

A maintainer session should register the stable address and watch both delivery
paths:

```redis
SADD agentbus:v1:agents agentbus:maintainer
HSET agentbus:v1:agent:agentbus:maintainer id agentbus:maintainer kind maintainer host local updated_at <iso8601>
ZADD agentbus:v1:agents:heartbeat <epoch_seconds> agentbus:maintainer
XGROUP CREATE agentbus:v1:agent:agentbus:maintainer:inbox inbox-agentbus-maintainer 0 MKSTREAM
XGROUP CREATE agentbus:v1:project:agentbus:channel:extension-requests:messages channel-extension-requests-agentbus-maintainer 0 MKSTREAM
```

Then read requests:

```redis
XREADGROUP GROUP inbox-agentbus-maintainer maintainer-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:agent:agentbus:maintainer:inbox >
XREADGROUP GROUP channel-extension-requests-agentbus-maintainer maintainer-main COUNT 20 BLOCK 5000 STREAMS agentbus:v1:project:agentbus:channel:extension-requests:messages >
```

## Replies And Status

Reply in the same `conversation` and set `reply_to` to the request
`message_id`. For status changes, use these event types:

```text
agentbus.extension.accepted
agentbus.extension.question
agentbus.extension.declined
agentbus.extension.done
```

Also update the request hash:

```redis
HSET agentbus:v1:request:<request_id> status accepted updated_at <iso8601> owner <maintainer_agent>
```

Use statuses:

```text
open
accepted
question
declined
done
blocked
```

## Search

Find open AgentBus extension requests:

```sh
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:project:agentbus:log + - MATCH "\"type\":\"agentbus.extension.request\"" WITHVALUES LIMIT 20
```

Find requests from one source project:

```sh
docker exec agentbus-redis redis-cli ARGREP agentbus:v1:project:aol-ko3:log + - MATCH "\"target_project\":\"agentbus\"" WITHVALUES LIMIT 20
```

Read the maintainer inbox:

```sh
docker exec agentbus-redis redis-cli XREVRANGE agentbus:v1:agent:agentbus:maintainer:inbox + - COUNT 10
```
