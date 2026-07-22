# Autonomous Agent-To-Agent Delivery

AgentBus carries messages (inboxes, `agentbus-emit`, `agentbus-poll`). The last
mile is *delivery*: getting an incoming message into an agent's context and
letting it act without a human relaying it. That last mile differs per agent, so
AgentBus keeps a stable core and one thin adapter per agent.

## The delivery contract

Every adapter does the same four things:

1. **Identity** — register as `<agent>@<instance>` so inboxes and heartbeats are
   distinct (see `docs/emitting.md`).
2. **Receive** — drain the relevant inboxes when the agent has a moment to act:
   its own loop tick, a scheduler, or a lifecycle hook.
3. **Act + reply** — handle the message and answer with
   `bin/agentbus-emit message`, reusing `conversation` and `--reply-to`.
4. **Switch** — a single enable/disable so the human stays in control.

## Claude Code adapter: Stop hook

Claude Code has no background loop; it only runs inside a turn. The natural
delivery point is the **Stop hook**, which fires when the model is about to
finish. `bin/agentbus-hook stop` reads the inbox there and, if there are new
messages, prints a block decision so the model keeps going, handles them, and
replies. A per-stream cursor makes the loop terminate: once drained, the next
stop returns nothing.

Wire it (see `bin/agentbus-hook install`):

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command",
        "command": "/abs/path/agentbus/bin/agentbus-hook stop --agent claude --instance <project>" } ] }
    ]
  }
}
```

Enable / disable / check (default is OFF, so wiring alone does nothing):

```sh
bin/agentbus-hook on     --agent claude --instance <project>
bin/agentbus-hook off    --agent claude --instance <project>
bin/agentbus-hook status --agent claude --instance <project>
```

## Kimi Code adapter: Stop hook (exit 2 + stderr)

Kimi Code has the same shape as Claude Code — no background loop, blockable
Stop hook — but a different hook contract: hooks live in
`~/.kimi-code/config.toml` as `[[hooks]]` entries, and a Stop hook blocks by
exiting with code `2`, passing the reason to the model via **stderr** instead
of a JSON decision on stdout. `bin/agentbus-hook --format kimi` implements
that contract with the same cursor logic:

```sh
bin/agentbus-hook install --agent kimi --instance <project> --format kimi
```

The global wiring for this machine lives in `~/.kimi-code/config.toml` and
derives the instance from the project directory name:

```toml
[[hooks]]
event = "Stop"
command = '/abs/path/agentbus/bin/agentbus-hook stop --agent kimi --instance "$(basename "$PWD")" --format kimi'
timeout = 10
```

The switch has two levels: `on --agent kimi` (no instance) sets the
agent-level default for all instances; `off --agent kimi --instance <project>`
opts a single project out. Without any key the default is OFF. On this
machine the agent level for `kimi` is ON. See `docs/adapters/kimi.md`.

## Loop-based agents (Hermes, and anything with a background tick)

Agents that already run a loop do not need a hook. They poll directly:

```sh
bin/agentbus-poll read --agent hermes --instance <project> --once
# handle, then reply with bin/agentbus-emit message ...
```

Wrap that in the agent's own loop and gate it with the same idea of an on/off
flag if you want a kill switch.

## Request/response agents (API-driven: Gemini, and similar)

Agents invoked per request (no persistent loop, no lifecycle hooks) are driven by
whatever schedules them: a cron tick or the surrounding orchestrator. On each
tick: `agentbus-poll ... --once`, act, `agentbus-emit message`. The cursor/ack
keeps them from re-processing.

## Adding a new agent

Pick the closest pattern above, then document the specifics under
`docs/adapters/<agent>.md`: how it registers identity, where it drains the
inbox, and how its on/off switch works. The transport and the message envelope
never change.
