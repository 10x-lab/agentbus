-include .env
export

AGENTBUS_REDIS_IMAGE ?= redis:8.8.0-alpine
AGENTBUS_REDIS_PORT ?= 6389
AGENTBUS_NS ?= agentbus:v1
AGENTBUS_CONTAINER ?= agentbus-redis

# Container runtime, agnostic to docker/podman. Override with
# AGENTBUS_CONTAINER_RUNTIME. Prefers the runtime that runs the container.
RT := $(shell \
  if [ -n "$$AGENTBUS_CONTAINER_RUNTIME" ]; then echo "$$AGENTBUS_CONTAINER_RUNTIME"; \
  elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx $(AGENTBUS_CONTAINER); then echo docker; \
  elif command -v podman >/dev/null 2>&1 && podman ps --format '{{.Names}}' 2>/dev/null | grep -qx $(AGENTBUS_CONTAINER); then echo podman; \
  elif command -v docker >/dev/null 2>&1; then echo docker; \
  elif command -v podman >/dev/null 2>&1; then echo podman; \
  else echo docker; fi)
COMPOSE := $(shell if [ "$(RT)" = podman ] && command -v podman-compose >/dev/null 2>&1; then echo podman-compose; else echo "$(RT) compose"; fi)

.PHONY: up down restart logs ping cli init smoke info runtime emit poll poll-maintainer poll-pending

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart redis

logs:
	$(COMPOSE) logs -f redis

ping:
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli PING

cli:
	$(RT) exec -it $(AGENTBUS_CONTAINER) redis-cli

runtime:
	@echo "runtime=$(RT) compose=$(COMPOSE) container=$(AGENTBUS_CONTAINER)"

init:
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli HSET $(AGENTBUS_NS):meta version 1 redis_image "$(AGENTBUS_REDIS_IMAGE)"
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli XGROUP CREATE $(AGENTBUS_NS):events export-jsonl 0 MKSTREAM || true

smoke:
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli XADD $(AGENTBUS_NS):events '*' ts "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" project agentbus agent make type smoke level info text "hello from stream"
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli ARINSERT $(AGENTBUS_NS):log "{\"ts\":\"$$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"project\":\"agentbus\",\"agent\":\"make\",\"type\":\"smoke\",\"level\":\"info\",\"text\":\"hello from array\"}"
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli ARGREP $(AGENTBUS_NS):log - + MATCH "hello" NOCASE WITHVALUES LIMIT 5

info:
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli INFO server
	$(RT) exec $(AGENTBUS_CONTAINER) redis-cli ARINFO $(AGENTBUS_NS):log || true

emit:
	@test -n "$(AGENT)" -a -n "$(PROJECT)" -a -n "$(TEXT)" || (echo "Usage: make emit PROJECT=<id> AGENT=<id> TEXT=<s> [TYPE=<t> INSTANCE=<id> PAYLOAD=<json>]"; exit 2)
	bin/agentbus-emit event --project "$(PROJECT)" --agent "$(AGENT)" --text "$(TEXT)" \
		$(if $(TYPE),--type "$(TYPE)") $(if $(INSTANCE),--instance "$(INSTANCE)") $(if $(PAYLOAD),--payload '$(PAYLOAD)')

poll:
	@test -n "$(AGENT)" || (echo "Usage: make poll AGENT=<agent_id> [PROJECT=<project_id> CHANNEL=<channel_id>]"; exit 2)
	@if [ -n "$(CHANNEL)" ]; then \
		bin/agentbus-poll read --agent "$(AGENT)" --project "$(PROJECT)" --channel "$(CHANNEL)"; \
	else \
		bin/agentbus-poll read --agent "$(AGENT)"; \
	fi

poll-pending:
	@test -n "$(AGENT)" || (echo "Usage: make poll-pending AGENT=<agent_id> [PROJECT=<project_id> CHANNEL=<channel_id>]"; exit 2)
	@if [ -n "$(CHANNEL)" ]; then \
		bin/agentbus-poll pending --agent "$(AGENT)" --project "$(PROJECT)" --channel "$(CHANNEL)"; \
	else \
		bin/agentbus-poll pending --agent "$(AGENT)"; \
	fi

poll-maintainer:
	bin/agentbus-poll read --agent agentbus:maintainer --project agentbus --channel extension-requests --consumer maintainer-main
