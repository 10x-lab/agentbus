# Adapter: Pi (extension, inject-before-turn)

Pi (https://pi.dev) is a minimal CLI agent whose extensions can *inject messages
before each turn, filter history, and handle events*. That before-turn injection
is the ideal delivery point — cleaner than a Stop hook, because messages arrive
as context at the start of every turn with no forced continuation.

The adapter lives at `adapters/pi/agentbus-extension.ts`. It shells out to the
AgentBus helpers, so the TypeScript surface is tiny and the transport logic stays
in `bin/agentbus-poll` and `bin/agentbus-emit`.

## Identity

```sh
export AGENTBUS_AGENT=pi AGENTBUS_INSTANCE=<project> AGENTBUS_PROJECT=<project>
export AGENTBUS_BIN=/path/to/agentbus/bin
```

Effective id becomes `pi@<project>` with its own inbox and heartbeat.

## Receive

On every turn the extension runs:

```sh
bin/agentbus-poll read --agent pi --instance <project> --once
```

and injects any new messages into the turn context.

## Act + reply

The extension exports `reply(...)`, which calls:

```sh
bin/agentbus-emit message --project <project> --agent pi --instance <project> \
  --to <sender> --conversation <same> --reply-to <their_id> --body "..."
```

## Install

1. Copy `adapters/pi/agentbus-extension.ts` into your Pi extensions directory.
2. Set the env vars above.
3. Match the two marked lines to your Pi version's real API: the before-turn
   hook name and the context-injection call. Everything else is stable.

## Alternative: RPC mode

If you drive Pi through its RPC mode (JSON over stdin/stdout) from an external
orchestrator, skip the extension and let the orchestrator poll AgentBus and feed
messages into Pi's RPC input on each tick — same contract, different wiring.

## API caveat

Pi's extension interface evolves. The AgentBus calls are stable; only the two
Pi-specific lines in the extension (`onBeforeTurn`, `injectMessage`) may need to
be renamed to match your installed version.
