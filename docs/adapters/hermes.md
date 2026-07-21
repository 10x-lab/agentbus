# Adapter: Hermes (loop-based)

Hermes runs its own background loop, so it needs no hook. It polls the bus on
each tick and replies with the emit helper. This is the reference for any
loop-based agent.

## Identity

Register as `hermes` (shared) or `hermes@<project>` per instance:

```sh
export AGENTBUS_AGENT=hermes AGENTBUS_INSTANCE=<project> AGENTBUS_PROJECT=<project>
```

## Receive: one poll per loop tick

Each iteration of Hermes's loop drains the inbox once and returns immediately:

```sh
bin/agentbus-poll read --agent hermes --instance <project> --once
```

Add project channels or a session inbox as needed:

```sh
bin/agentbus-poll read --agent hermes --instance <project> \
  --session <session_id> --project <project> --channel general --once
```

Messages are delivered through a consumer group, so each message is handed to
Hermes exactly once across restarts.

## Act + reply

Handle the message, then answer on the same conversation:

```sh
bin/agentbus-emit message --project <project> --agent hermes --instance <project> \
  --to <sender> --conversation <same_conversation> --reply-to <their_message_id> \
  --subject "re: ..." --body "..." --text "hermes -> <sender>: reply"
```

Acknowledge only after the message is fully handled:

```sh
bin/agentbus-poll ack --agent hermes \
  --stream agentbus:v1:agent:hermes@<project>:inbox --id <stream_id>
```

## Switch

Gate the poll in Hermes's loop behind the same on/off idea as the Claude hook, so
you keep a kill switch. A simple Redis flag works:

```sh
docker exec agentbus-redis redis-cli SET agentbus:v1:hook:hermes@<project>:enabled 1
# in the loop: skip polling when the flag is not "1"
```

## Minimal loop sketch

```sh
while true; do
  enabled=$(docker exec agentbus-redis redis-cli GET agentbus:v1:hook:hermes@proj:enabled)
  if [ "$enabled" = "1" ]; then
    bin/agentbus-poll read --agent hermes --instance proj --once | handle_messages
  fi
  sleep 5
done
```

`handle_messages` is Hermes-specific: parse the stream entries, act, reply with
`agentbus-emit`, then `ack`.
