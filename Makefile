-include .env
export

AGENTBUS_REDIS_IMAGE ?= redis:8.8.0-alpine
AGENTBUS_REDIS_PORT ?= 6389
AGENTBUS_NS ?= agentbus:v1

.PHONY: up down restart logs ping cli init smoke info poll poll-maintainer poll-pending

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart redis

logs:
	docker compose logs -f redis

ping:
	docker exec agentbus-redis redis-cli PING

cli:
	docker exec -it agentbus-redis redis-cli

init:
	docker exec agentbus-redis redis-cli HSET $(AGENTBUS_NS):meta version 1 redis_image "$(AGENTBUS_REDIS_IMAGE)"
	docker exec agentbus-redis redis-cli XGROUP CREATE $(AGENTBUS_NS):events export-jsonl 0 MKSTREAM || true

smoke:
	docker exec agentbus-redis redis-cli XADD $(AGENTBUS_NS):events '*' ts "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" project agentbus agent make type smoke level info text "hello from stream"
	docker exec agentbus-redis redis-cli ARINSERT $(AGENTBUS_NS):log "{\"ts\":\"$$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"project\":\"agentbus\",\"agent\":\"make\",\"type\":\"smoke\",\"level\":\"info\",\"text\":\"hello from array\"}"
	docker exec agentbus-redis redis-cli ARGREP $(AGENTBUS_NS):log - + MATCH "hello" NOCASE WITHVALUES LIMIT 5

info:
	docker exec agentbus-redis redis-cli INFO server
	docker exec agentbus-redis redis-cli ARINFO $(AGENTBUS_NS):log || true

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
