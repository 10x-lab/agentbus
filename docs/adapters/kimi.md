# Adapter: Kimi Code (Stop hook, exit-2 blocking)

Kimi Code is turn-based like Claude Code: no background loop, but it has
lifecycle hooks configured in `~/.kimi-code/config.toml`. Its `Stop` event is
blockable — a hook that exits with code `2` blocks the stop, and the text it
prints on **stderr** is handed back to the model as the reason to continue.
That is the delivery point.

The adapter is `bin/agentbus-hook` with `--format kimi`. It is the same script
Claude Code uses; only the output contract changes (stderr + exit 2 instead of
a `{"decision":"block"}` JSON on stdout). The cursor logic that makes the loop
terminate once the inbox is drained is identical.

## Identity

Effective id is `kimi@<project>` (shared inbox `agent:kimi:inbox` plus the
instance inbox `agent:kimi@<project>:inbox`). Register and heartbeat happen
through `bin/agentbus-emit` / `bin/agentbus-poll` as for every other agent.

## Receive

Wire the Stop hook:

```sh
bin/agentbus-hook install --agent kimi --instance <project> --format kimi
```

which prints the snippet to add to `~/.kimi-code/config.toml`:

```toml
[[hooks]]
event = "Stop"
command = "/abs/path/agentbus/bin/agentbus-hook stop --agent kimi --instance <project> --format kimi"
timeout = 10
```

When the model is about to finish a turn, the hook drains the inbox. If there
are new messages it prints them on stderr and exits `2`, so Kimi Code keeps
the turn going and the messages land in context. Once drained, the next stop
exits `0` and the turn ends normally.

Note: Kimi Code hooks are fail-open — if the script errors or times out, the
turn is allowed to end. The on/off switch below is the real guardrail.

## Act + reply

Same contract as every adapter:

```sh
bin/agentbus-emit message --project <project> --agent kimi --instance <project> \
  --to <sender> --conversation <same> --reply-to <their_id> --body "..."
```

## Switch

The switch is a Redis key, independent of the CLI. There are two levels:

- **Agent level** (default for every instance): `bin/agentbus-hook on --agent kimi`
  sets the default for all `kimi@<project>` instances that have no
  per-instance key. On this machine the agent level is ON.
- **Per instance**: `bin/agentbus-hook off --agent kimi --instance <project>`
  opts a single project out (a per-instance `0` always wins over the agent
  default); `on` with the same flags opts it back in explicitly.

```sh
bin/agentbus-hook status --agent kimi                        # agent-level default
bin/agentbus-hook status --agent kimi --instance <project>   # effective state
```

Without any key at all the default is OFF, so wiring the hook alone does
nothing until the agent level (or an instance) is switched on.

## Polling

The Stop hook covers delivery while a turn is running. For everything else,
poll explicitly with the portable helper — at session start, before asking the
user for context, and before/after long work:

```sh
bin/agentbus-poll read --agent kimi --instance <project> --once
bin/agentbus-poll read --agent kimi --instance <project> --project <project> --channel <channel> --once
bin/agentbus-poll pending --agent kimi --instance <project>
```

Acknowledge only after handling:

```sh
bin/agentbus-poll ack --agent kimi --instance <project> \
  --stream agentbus:v1:agent:kimi@<project>:inbox --id <stream_id>
```

See `docs/polling.md` for the full contract.
