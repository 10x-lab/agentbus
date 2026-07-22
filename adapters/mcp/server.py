#!/usr/bin/env python3
"""
AgentBus MCP Server — Model Context Protocol bridge for AgentBus.

Exposes AgentBus as MCP tools so agents that are MCP-capable but have no loop
or lifecycle hook (ZCode, Gemini, Codex) can participate in the bus.

Protocol: JSON-RPC 2.0 over stdio (pure stdlib, zero dependencies).
Operations shell out to bin/agentbus-emit and bin/agentbus-poll, keeping the
core transport logic in one place.

Tools:
  agentbus_inbox_read   — drain the agent's inbox
  agentbus_send         — send a message to another agent
  agentbus_reply        — reply to a message in a conversation
  agentbus_register     — register identity / heartbeat / check status

Environment:
  AGENTBUS_AGENT       agent id, e.g. zcode, gemini, codex
  AGENTBUS_INSTANCE    optional instance suffix (→ agent@instance)
  AGENTBUS_PROJECT     project slug
  AGENTBUS_BIN         path to bin/ dir (default: <repo>/bin)
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AGENTBUS_BIN = os.environ.get(
    "AGENTBUS_BIN",
    os.path.join(os.path.dirname(__file__), "..", "..", "bin"),
)
AGENTBUS_CONTAINER = os.environ.get("AGENTBUS_CONTAINER", "agentbus-redis")

_RUNTIME_CACHE: str | None = None


def _container_runtime() -> str:
    """Detect the container runtime (docker or podman), agnostic to the host.

    Order: explicit AGENTBUS_CONTAINER_RUNTIME, then whichever runtime actually
    runs the agentbus container, then the first available binary.
    """
    global _RUNTIME_CACHE
    if _RUNTIME_CACHE:
        return _RUNTIME_CACHE

    override = os.environ.get("AGENTBUS_CONTAINER_RUNTIME")
    if override:
        _RUNTIME_CACHE = override
        return override

    for rt in ("docker", "podman"):
        if not shutil.which(rt):
            continue
        try:
            out = subprocess.run(
                [rt, "ps", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            ).stdout.splitlines()
            if AGENTBUS_CONTAINER in out:
                _RUNTIME_CACHE = rt
                return rt
        except Exception:
            continue

    for rt in ("docker", "podman"):
        if shutil.which(rt):
            _RUNTIME_CACHE = rt
            return rt

    _RUNTIME_CACHE = "docker"
    return _RUNTIME_CACHE
AGENT = os.environ.get("AGENTBUS_AGENT", "mcp-agent")
INSTANCE = os.environ.get("AGENTBUS_INSTANCE", "")
PROJECT = os.environ.get("AGENTBUS_PROJECT", "")

EFFECTIVE = f"{AGENT}@{INSTANCE}" if INSTANCE else AGENT


# ---------------------------------------------------------------------------
# Shell helpers (same pattern as adapters/pi/agentbus-extension.ts)
# ---------------------------------------------------------------------------
def _run(argv: list[str], stdin_data: str | None = None) -> str:
    """Run a command, return stripped stdout. Raises on non-zero exit."""
    result = subprocess.run(
        argv,
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"exit {result.returncode}")
    return result.stdout.strip()


def _agentbus_emit(args: list[str]) -> str:
    """Run bin/agentbus-emit with common agent/project context.

    The emit script requires the command (event|message) as the first positional
    argument, before any flags.
    """
    if not args or args[0] not in ("event", "message"):
        raise ValueError("first arg must be 'event' or 'message'")
    cmd = args[0]
    rest = args[1:]
    argv = [
        f"{AGENTBUS_BIN}/agentbus-emit",
        cmd,
        "--project", PROJECT,
        "--agent", AGENT,
    ]
    if INSTANCE:
        argv += ["--instance", INSTANCE]
    argv += rest
    return _run(argv)


def _agentbus_poll(args: list[str]) -> list[dict]:
    """Run bin/agentbus-poll, parse multi-line XREADGROUP output into messages.

    The poll script requires the command (read|ack|pending) as the first
    positional argument, before any flags.
    """
    if not args or args[0] not in ("read", "ack", "pending"):
        raise ValueError("first arg must be 'read', 'ack', or 'pending'")
    cmd = args[0]
    rest = args[1:]
    argv = [f"{AGENTBUS_BIN}/agentbus-poll", cmd]
    if INSTANCE:
        argv += ["--instance", INSTANCE]
    argv += ["--agent", AGENT] + rest
    raw = _run(argv)
    return _parse_xreadgroup(raw)


def _parse_xreadgroup(raw: str) -> list[dict]:
    """Parse `redis-cli --raw XREADGROUP` output into a list of message dicts.

    Output format (--raw, newline-separated):
      stream_key
      stream_id
      field1
      value1
      field2
      value2
      ...
    Messages are terminated by the next stream_key or EOF.
    """
    lines = [l for l in raw.split("\n") if l.strip()]
    messages: list[dict] = []
    i = 0
    while i < len(lines):
        # Each message starts with a stream key line
        stream_key = lines[i]
        i += 1
        # Followed by stream_id (e.g. "1784632243452-0")
        if i >= len(lines):
            break
        stream_id = lines[i]
        i += 1
        # Then field/value pairs. We look ahead to detect the next stream_key
        # (a line ending with a Redis key pattern) or a field count line.
        fields: dict[str, str] = {}
        while i < len(lines):
            # Check if next line looks like a stream key (contains ":" and no space)
            # or a raw count digit (redis-cli --raw sometimes emits item counts)
            peek = lines[i]
            if ":" in peek and " " not in peek and not peek.replace("-", "").replace("0", "").replace("1", "").replace("2", "").replace("3", "").replace("4", "").replace("5", "").replace("6", "").replace("7", "").replace("8", "").replace("9", "").replace(".", ""):
                # Looks like a stream key (contains colons), break
                break
            if peek.isdigit() and i + 1 < len(lines) and ":" in lines[i + 1]:
                # This is a count line before the next stream key
                i += 1
                break
            # Must be field/value pair
            if i + 1 >= len(lines):
                break
            key = lines[i]
            val = lines[i + 1]
            fields[key] = val
            i += 2

        if fields:
            fields["_stream"] = stream_key
            fields["_stream_id"] = stream_id
            messages.append(fields)
    return messages


def _ack_message(stream: str, stream_id: str) -> None:
    """Acknowledge a message after handling."""
    _run([
        f"{AGENTBUS_BIN}/agentbus-poll",
        "ack",
        "--agent", AGENT,
        "--stream", stream,
        "--id", stream_id,
    ] + (["--instance", INSTANCE] if INSTANCE else []))


# ---------------------------------------------------------------------------
# MCP protocol helpers
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    """Write to stderr (MCP uses stdout for protocol, stderr for logging)."""
    print(f"[agentbus-mcp] {msg}", file=sys.stderr, flush=True)


def _send_jsonrpc(data: dict) -> None:
    """Send a JSON-RPC message to stdout."""
    line = json.dumps(data, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _error(id_, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": {"code": code, "message": message},
    }


def _result(id_, result) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def tool_inbox_read(args: dict) -> str:
    """Read new messages from the agent's AgentBus inbox.

    Args (all optional):
      ack: if "true", acknowledge messages after reading (default: false)
    """
    do_ack = args.get("ack", "false").lower() == "true"
    try:
        messages = _agentbus_poll(["read", "--once"])
    except RuntimeError as e:
        return f"Error reading inbox: {e}"

    if not messages:
        return "No new messages in inbox."

    # Acknowledge if requested
    if do_ack:
        for msg in messages:
            try:
                _ack_message(msg["_stream"], msg["_stream_id"])
            except RuntimeError:
                pass  # best-effort ack

    # Format for agent consumption
    lines = [f"{len(messages)} message(s):"]
    for i, msg in enumerate(messages, 1):
        lines.append(f"\n--- Message {i} ---")
        for k, v in msg.items():
            if k.startswith("_"):
                continue
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def tool_send(args: dict) -> str:
    """Send a message to another agent via AgentBus.

    Required:
      to: recipient agent id (e.g. "claude@agentbus" or "codex")
      subject: short subject line
      body: message body text

    Optional:
      conversation: conversation id for threading (auto-generated if omitted)
      channel: project channel id instead of direct message
    """
    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    conversation = args.get("conversation", "")
    channel = args.get("channel", "")

    if not to and not channel:
        return "Error: either 'to' or 'channel' is required."
    if not subject:
        return "Error: 'subject' is required."
    if not body:
        return "Error: 'body' is required."

    text = f"{EFFECTIVE} -> {to or f'#{channel}'}: {subject}"

    emit_args = ["message", "--text", text, "--subject", subject, "--body", body]

    if channel:
        emit_args += ["--channel", channel]
    else:
        emit_args += ["--to", to]

    if conversation:
        emit_args += ["--conversation", conversation]

    try:
        msg_id = _agentbus_emit(emit_args)
        return f"Message sent. id={msg_id}"
    except RuntimeError as e:
        return f"Error sending message: {e}"


def tool_reply(args: dict) -> str:
    """Reply to a message in an existing conversation.

    Required:
      to: recipient agent id (the original sender)
      conversation: conversation id (must match the original)
      reply_to: message_id of the message being replied to
      body: reply body text

    Optional:
      subject: subject (defaults to "Re: <original subject>" if omitted)
    """
    to = args.get("to", "")
    conversation = args.get("conversation", "")
    reply_to = args.get("reply_to", "")
    body = args.get("body", "")
    subject = args.get("subject", f"Re")

    if not to:
        return "Error: 'to' is required."
    if not conversation:
        return "Error: 'conversation' is required."
    if not reply_to:
        return "Error: 'reply_to' is required."
    if not body:
        return "Error: 'body' is required."

    text = f"{EFFECTIVE} -> {to}: {subject}"

    emit_args = [
        "message",
        "--to", to,
        "--text", text,
        "--subject", subject,
        "--body", body,
        "--conversation", conversation,
        "--reply-to", reply_to,
    ]

    try:
        msg_id = _agentbus_emit(emit_args)
        return f"Reply sent. id={msg_id}, conversation={conversation}"
    except RuntimeError as e:
        return f"Error sending reply: {e}"


def tool_register(args: dict) -> str:
    """Register or check this agent on AgentBus.

    Without arguments: show current status (identity, heartbeat).
    With heartbeat=true: emit a heartbeat event.

    Args (all optional):
      heartbeat: "true" to emit a fresh heartbeat event
    """
    do_heartbeat = args.get("heartbeat", "false").lower() == "true"

    # Check current heartbeat
    try:
        hb_raw = _run([
            _container_runtime(), "exec", AGENTBUS_CONTAINER, "redis-cli",
            "ZSCORE", "agentbus:v1:agents:heartbeat", EFFECTIVE,
        ])
    except RuntimeError:
        hb_raw = ""

    info_lines = [
        f"Agent: {EFFECTIVE}",
        f"Instance: {INSTANCE or '(shared)'}",
        f"Project: {PROJECT or '(not set)'}",
        f"Last heartbeat epoch: {hb_raw or 'never'}",
    ]

    if do_heartbeat:
        try:
            _agentbus_emit([
                "event",
                "--type", "heartbeat",
                "--text", f"{EFFECTIVE} heartbeat",
            ])
            info_lines.append("Heartbeat emitted ✓")
        except RuntimeError as e:
            info_lines.append(f"Heartbeat failed: {e}")

    # Also check inbox status
    try:
        pending_raw = _run([
            f"{AGENTBUS_BIN}/agentbus-poll",
            "pending",
            "--agent", AGENT,
        ] + (["--instance", INSTANCE] if INSTANCE else []))
        info_lines.append(f"\nPending messages:\n{pending_raw}")
    except RuntimeError:
        info_lines.append("\nPending messages: (could not read)")

    return "\n".join(info_lines)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "agentbus_inbox_read",
        "description": (
            "Read new messages from your AgentBus inbox. "
            "Call this at the start of each session or when you want to check "
            "for messages from other agents. Set ack=true to acknowledge after reading."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ack": {
                    "type": "string",
                    "description": "Set to 'true' to acknowledge messages after reading.",
                },
            },
        },
    },
    {
        "name": "agentbus_send",
        "description": (
            "Send a message to another agent or project channel via AgentBus. "
            "Use this to coordinate, ask questions, or hand off work to other agents. "
            "Messages are durable and survive disconnects."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": (
                        "Recipient agent id (e.g. 'claude@agentbus', 'codex'). "
                        "Required unless 'channel' is set."
                    ),
                },
                "subject": {
                    "type": "string",
                    "description": "Short subject line for the message.",
                },
                "body": {
                    "type": "string",
                    "description": "Message body text.",
                },
                "conversation": {
                    "type": "string",
                    "description": (
                        "Conversation id for threading. Auto-generated if omitted."
                    ),
                },
                "channel": {
                    "type": "string",
                    "description": (
                        "Project channel id instead of a direct message. "
                        "Use for broadcast-style communication."
                    ),
                },
            },
            "required": ["subject", "body"],
        },
    },
    {
        "name": "agentbus_reply",
        "description": (
            "Reply to a message in an existing AgentBus conversation. "
            "Always include the conversation id and the message_id you are replying to."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient agent id (the original sender).",
                },
                "conversation": {
                    "type": "string",
                    "description": "Conversation id (must match the original message).",
                },
                "reply_to": {
                    "type": "string",
                    "description": "Message id of the message being replied to.",
                },
                "body": {
                    "type": "string",
                    "description": "Reply body text.",
                },
                "subject": {
                    "type": "string",
                    "description": "Subject (defaults to 'Re').",
                },
            },
            "required": ["to", "conversation", "reply_to", "body"],
        },
    },
    {
        "name": "agentbus_register",
        "description": (
            "Check your AgentBus registration status and heartbeat. "
            "Call at session start to verify connectivity. "
            "Set heartbeat=true to emit a fresh heartbeat."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "heartbeat": {
                    "type": "string",
                    "description": "Set to 'true' to emit a heartbeat event.",
                },
            },
        },
    },
]

TOOL_MAP = {
    "agentbus_inbox_read": tool_inbox_read,
    "agentbus_send": tool_send,
    "agentbus_reply": tool_reply,
    "agentbus_register": tool_register,
}


# ---------------------------------------------------------------------------
# JSON-RPC dispatch
# ---------------------------------------------------------------------------
def handle_request(msg: dict) -> dict | None:
    """Handle a JSON-RPC request. Returns response or None for notifications."""
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    _log(f"<- {method} id={req_id}")

    try:
        if method == "initialize":
            return _result(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "agentbus-mcp",
                    "version": "1.0.0",
                },
            })

        elif method == "notifications/initialized":
            # No response for notifications
            _log("Client initialized, ready")
            return None

        elif method == "tools/list":
            return _result(req_id, {"tools": TOOLS})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            tool_fn = TOOL_MAP.get(tool_name)
            if not tool_fn:
                return _error(req_id, -32601, f"Unknown tool: {tool_name}")
            try:
                output = tool_fn(tool_args)
                return _result(req_id, {
                    "content": [{"type": "text", "text": output}],
                })
            except Exception as e:
                return _result(req_id, {
                    "content": [{"type": "text", "text": f"Tool error: {e}"}],
                    "isError": True,
                })

        elif method == "ping":
            return _result(req_id, {})

        else:
            return _error(req_id, -32601, f"Unknown method: {method}")

    except Exception as e:
        _log(f"ERROR in {method}: {e}")
        return _error(req_id, -32603, str(e))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    _log(f"AgentBus MCP server starting: agent={EFFECTIVE} project={PROJECT}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _log(f"Invalid JSON on stdin: {line[:200]}")
            continue

        response = handle_request(msg)
        if response is not None:
            _send_jsonrpc(response)

    _log("stdin closed, shutting down")


if __name__ == "__main__":
    main()
