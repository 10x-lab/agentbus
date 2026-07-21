/**
 * AgentBus adapter for Pi (https://pi.dev).
 *
 * Pi extensions can inject messages before each turn. This one drains the
 * agent's AgentBus inbox on every turn and injects any new messages as context,
 * so a human never has to relay them. Replies go back out with agentbus-emit.
 *
 * It shells out to the language-agnostic AgentBus helpers so the TypeScript
 * surface stays tiny and the transport logic lives in one place:
 *   - bin/agentbus-poll  (receive)
 *   - bin/agentbus-emit   (send)
 *
 * NOTE: the exact Pi extension API (hook names, registration) evolves; adjust
 * the two marked lines to match your installed Pi version. The AgentBus calls
 * below are stable.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const run = promisify(execFile);

// --- configure for this Pi instance -----------------------------------------
const AGENTBUS_BIN = process.env.AGENTBUS_BIN ?? "/Users/lavoro/Documents/agentbus/bin";
const AGENT = process.env.AGENTBUS_AGENT ?? "pi";
const INSTANCE = process.env.AGENTBUS_INSTANCE ?? ""; // e.g. project slug
const PROJECT = process.env.AGENTBUS_PROJECT ?? "";
const EFFECTIVE = INSTANCE ? `${AGENT}@${INSTANCE}` : AGENT;

async function drainInbox(): Promise<string> {
  const args = ["read", "--agent", AGENT, "--once"];
  if (INSTANCE) args.push("--instance", INSTANCE);
  try {
    const { stdout } = await run(`${AGENTBUS_BIN}/agentbus-poll`, args);
    return stdout.trim();
  } catch {
    return ""; // bus unavailable: stay silent, do not block the turn
  }
}

export async function reply(opts: {
  to: string;
  conversation?: string;
  replyTo?: string;
  subject?: string;
  body: string;
}): Promise<void> {
  const args = [
    "message",
    "--project", PROJECT,
    "--agent", AGENT,
    ...(INSTANCE ? ["--instance", INSTANCE] : []),
    "--to", opts.to,
    "--text", `${EFFECTIVE} -> ${opts.to}`,
    "--body", opts.body,
  ];
  if (opts.conversation) args.push("--conversation", opts.conversation);
  if (opts.replyTo) args.push("--reply-to", opts.replyTo);
  if (opts.subject) args.push("--subject", opts.subject);
  await run(`${AGENTBUS_BIN}/agentbus-emit`, args);
}

// --- Pi wiring: inject inbox before each turn --------------------------------
// Replace `onBeforeTurn` with your Pi version's before-turn hook name.
export default function register(pi: any) {
  pi.onBeforeTurn?.(async (ctx: any) => {           // <-- Pi API: before-turn hook
    const inbox = await drainInbox();
    if (inbox) {
      ctx.injectMessage?.(                            // <-- Pi API: inject context
        `AgentBus: new inbox messages for ${EFFECTIVE}. Read them, act, and reply ` +
        `by importing { reply } from this extension.\n\n${inbox}`,
      );
    }
  });
}
