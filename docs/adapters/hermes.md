# Adapter: Hermes (loop-based, native daemon)

Hermes è un agente loop-based: ha un suo ciclo interno ma non ha un hook di
stop come Claude Code. L'adapter nativo è un demone standalone
(`agentbus-hermes-poll`) che fa polling della inbox e risponde in autonomia.

Il demone rimpiazza completamente il pattern a cron job descritto nella prima
versione di questo documento. Non serve più `agentbus-poll` manuale né cron.

## Avvio Rapido

```sh
# Avvia il demone (forever, background)
adapters/hermes/agentbus-hermes-poll start --agent hermes --project aol-api --interval 2

# Stato
adapters/hermes/agentbus-hermes-poll status

# Ferma
adapters/hermes/agentbus-hermes-poll stop
```

## Come Funziona

Il demone fa un loop infinito:

1. **Registrazione** — assicura che hermes sia registrato in AgentBus
   (SADD, HSET, ZADD heartbeat, XGROUP CREATE inbox)
2. **Polling** — `XREADGROUP` sulla inbox `agentbus:v1:agent:hermes:inbox`
   con consumer group `inbox-hermes`
3. **Process** — per ogni messaggio ricevuto:
   - Emette evento `message.received`
   - Per messaggi diretti da altri agenti: risponde con `agentbus-emit message`
   - Salta i self-message per evitare loop
   - Fa ACK (`XACK`)
4. **Sleep** — pausa configurabile (default 2s)

## Auto-Reply

Il demone risponde automaticamente ai messaggi diretti con una conferma di
ricezione. Per messaggi che richiedono elaborazione complessa, si può
estendere la funzione `process_message()` per chiamare `hermes chat -q`.

## Auto-Start (macOS launchd)

```sh
# Copia il plist
cp adapters/hermes/com.agentbus.hermes-poll.plist ~/Library/LaunchAgents/

# Carica
launchctl load ~/Library/LaunchAgents/com.agentbus.hermes-poll.plist
```

## Log

```
/tmp/agentbus-hermes-poll.log   — log del demone
/tmp/agentbus-hermes-poll.stats — contatore messaggi processati
```
