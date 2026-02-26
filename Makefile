SHELL := /bin/sh

APP_PROFILE ?= dev
ADMIN_USER ?= admin
ADMIN_PASS ?= ChangeMe123!

.PHONY: doctor up down restart ps logs health wait-api first-run bootstrap-admin install-hooks guard-staged guard-all

doctor:
	@./infra/scripts/doctor.sh

up:
	@cd infra && APP_PROFILE=$(APP_PROFILE) ./scripts/compose.sh up -d --build

down:
	@cd infra && APP_PROFILE=$(APP_PROFILE) ./scripts/compose.sh down

restart:
	@cd infra && APP_PROFILE=$(APP_PROFILE) ./scripts/compose.sh down && APP_PROFILE=$(APP_PROFILE) ./scripts/compose.sh up -d --build

ps:
	@cd infra && APP_PROFILE=$(APP_PROFILE) ./scripts/compose.sh ps

logs:
	@cd infra && APP_PROFILE=$(APP_PROFILE) ./scripts/compose.sh logs -f --tail=200

health:
	@curl -fsS http://localhost:8000/api/health | jq . || curl -fsS http://localhost:8000/api/health

wait-api:
	@i=0; \
	until curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; do \
	  i=$$((i+1)); \
	  if [ $$i -ge 60 ]; then \
	    echo "API healthcheck timeout (120s)"; \
	    exit 1; \
	  fi; \
	  sleep 2; \
	done; \
	echo "API is healthy"

first-run: doctor up wait-api
	@echo "다음 단계: make bootstrap-admin ADMIN_USER=admin ADMIN_PASS='ChangeMe123!'"

bootstrap-admin:
	@cd infra && APP_PROFILE=$(APP_PROFILE) ./scripts/compose.sh exec -T api sh -lc "cd /app && python scripts/bootstrap_admin.py --username '$(ADMIN_USER)' --password '$(ADMIN_PASS)'"

install-hooks:
	@git config core.hooksPath .githooks
	@chmod +x .githooks/pre-commit .githooks/pre-push scripts/check_sensitive_guard.sh
	@echo "git hooks installed (.githooks)"

guard-staged:
	@./scripts/check_sensitive_guard.sh --staged

guard-all:
	@./scripts/check_sensitive_guard.sh --all
