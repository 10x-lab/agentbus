# Adapter: MCP Server (tools, stdio JSON-RPC)

Agents that are MCP-capable but have no background loop or lifecycle hook
(ZCode, Gemini, Codex, and any MCP client) use this server as a bridge.
It exposes AgentBus operations as MCP tools over stdio JSON-RPC.

The server lives at `adapters/mcp/server.py`. It is a single file, pure stdlib
Python 3, zero dependencies. It shells out to `bin/agentbus-emit` and
`bin/agentbus-poll`, exactly like the Pi extension — the transport logic stays
in one place.

## Tools

| Tool                   | What it does                              |
|------------------------|-------------------------------------------|
| `agentbus_inbox_read`  | Drain the agent's inbox, return messages  |
| `agentbus_send`        | Send a message to another agent or channel|
| `agentbus_reply`       | Reply to a message in a conversation      |
| `agentbus_register`    | Show agent status, emit heartbeat         |

## Identity

Set these environment variables before launching the MCP server:

```sh
export AGENTBUS_AGENT=zcode        # or gemini, codex, ...
export AGENTBUS_INSTANCE=myproject # optional, → agent@instance
export AGENTBUS_PROJECT=myproject  # project slug
export AGENTBUS_BIN=/path/to/agentbus/bin
```

Effective identity becomes `zcode@myproject` (or just `zcode` without instance).

## Install (per agent)

### ZCode

Add to ZCode MCP settings:

```json
{
  "mcpServers": {
    "agentbus": {
      "command": "python3",
      "args": ["/absolute/path/to/adapters/mcp/server.py"],
      "env": {
        "AGENTBUS_AGENT": "zcode",
        "AGENTBUS_PROJECT": "myproject"
      }
    }
  }
}
```

### Gemini CLI

```json
{
  "mcpServers": {
    "agentbus": {
      "command": "python3",
      "args": ["/absolute/path/to/adapters/mcp/server.py"],
      "env": {
        "AGENTBUS_AGENT": "gemini",
        "AGENTBUS_PROJECT": "myproject"
      }
    }
  }
}
```

### Codex (OpenAI)

Same pattern — point the MCP server config to this script with the right env vars.

## Protocol

The server speaks JSON-RPC 2.0 over stdio:

- **stdin**: JSON-RPC requests, one JSON object per line
- **stdout**: JSON-RPC responses, one JSON object per line
- **stderr**: human-readable logs

MCP methods implemented:

| Method                    | Purpose                     |
|---------------------------|-----------------------------|
| `initialize`              | Handshake, capabilities     |
| `notifications/initialized` | Post-handshake ack       |
| `tools/list`              | List the 4 AgentBus tools   |
| `tools/call`              | Invoke a specific tool      |
| `ping`                    | Liveness check              |

## How the agent uses it

1. Agent starts → MCP client spawns `server.py` as subprocess.
2. Agent calls `agentbus_register` (heartbeat=true) to announce itself.
3. At the start of each session (or before work), agent calls
   `agentbus_inbox_read` to check for messages.
4. When it needs to coordinate, it calls `agentbus_send` or `agentbus_reply`.
5. Messages are durable — even if the agent disconnects and reconnects later,
   pending messages are still waiting in Redis.

No loop is needed. The agent drives the bus at its own cadence, just like it
would call any other MCP tool.

## Test (standalone)

Pipe JSON-RPC to the server and check responses:

```sh
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}' | \
  AGENTBUS_PROJECT=agentbus AGENTBUS_AGENT=test-mcp python3 adapters/mcp/server.py
```

## Design note

This adapter is intentionally thin. It does not reimplement emit/poll logic.
The MCP protocol layer is pure stdlib. All writes go through
`bin/agentbus-emit` (with its atomic Lua EVAL) and all reads through
`bin/agentbus-poll` (with its consumer-group polling). The only new code is
the JSON-RPC bridge and the tool argument mapping.
