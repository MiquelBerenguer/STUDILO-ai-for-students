.PHONY: help setup dev backend frontend test lint migrate check secrets-scan

BACKEND := backend
FRONTEND := frontend
# Per-worktree overrides (gitignored), e.g. "BACKEND_PORT := 8003" so parallel worktrees can all run `make dev`.
-include .worktree.mk
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173
export BACKEND_PORT FRONTEND_PORT

help:
	@echo "make setup   - create .env (with APP_SECRET_KEY), install backend + frontend deps"
	@echo "make dev     - validate config, run backend :$(BACKEND_PORT) and frontend :$(FRONTEND_PORT) (LAN-exposed)"
	@echo "make test    - backend tests + frontend typecheck/build"
	@echo "make lint    - ruff + tsc"
	@echo "make check   - validate .env + models.yaml without starting"

setup:
	@command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }
	@command -v npm >/dev/null || { echo "Node.js >= 20 (npm) is required"; exit 1; }
	@test -f .env || { cp .env.example .env; echo "created .env from .env.example — fill in your provider keys"; }
	@uv run --no-project --python 3.12 python scripts/ensure_secret.py
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm install --no-fund --no-audit

check:
	cd $(BACKEND) && uv run python -m app.startup

dev: setup check
	@echo "Backend http://localhost:$(BACKEND_PORT)  ·  Frontend http://localhost:$(FRONTEND_PORT)"
	@trap 'kill 0' INT TERM EXIT; \
	  (cd $(BACKEND) && uv run uvicorn app.main:app --host 127.0.0.1 --port $(BACKEND_PORT) --reload --reload-dir app) & \
	  (cd $(FRONTEND) && npm run dev -- --host --port $(FRONTEND_PORT) --strictPort) & \
	  wait

test:
	cd $(BACKEND) && uv run pytest -q
	cd $(FRONTEND) && npm run typecheck && npm run build

lint:
	cd $(BACKEND) && uv run ruff check app tests
	cd $(FRONTEND) && npm run typecheck

migrate:
	cd $(BACKEND) && uv run alembic upgrade head

secrets-scan:
	@command -v gitleaks >/dev/null || { echo "install gitleaks: brew install gitleaks"; exit 1; }
	# History before the v1 pivot (eff5d11) contains committed .env files; see PLAN.md A1 (rotate those keys).
	gitleaks git . --no-banner --redact --log-opts="eff5d11..HEAD"
	gitleaks git . --no-banner --redact --pre-commit --staged
