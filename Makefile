.PHONY: help setup dev backend frontend test lint migrate check secrets-scan

BACKEND := backend
FRONTEND := frontend
# View worktrees (see AGENTS.md) have a gitignored .worktree.mk that sets WORKTREE_VIEW and FRONTEND_PORT.
# A worktree never runs its own backend: it previews its frontend against the MAIN backend + shared database.
-include .worktree.mk
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173
MAIN_BACKEND_PORT ?= 8000
export BACKEND_PORT FRONTEND_PORT

help:
	@echo "make setup   - create .env (with APP_SECRET_KEY), install backend + frontend deps"
	@echo "make dev     - validate config, run backend :$(BACKEND_PORT) and frontend :$(FRONTEND_PORT) (LAN-exposed)"
	@echo "make test    - backend tests + frontend typecheck/build"
	@echo "make lint    - ruff + tsc"
	@echo "make check   - validate .env + models.yaml without starting"

ifdef WORKTREE_VIEW
setup:
	@echo "Worktree '$(WORKTREE_VIEW)': dependencies are shared with the main checkout (see AGENTS.md). Nothing to install."

dev:
	@curl -fs http://127.0.0.1:$(MAIN_BACKEND_PORT)/api/v1/health >/dev/null || { \
	  echo "The main backend isn't running. Start it in the main checkout: make dev"; exit 1; }
	@echo "Worktree '$(WORKTREE_VIEW)': this branch's frontend on http://localhost:$(FRONTEND_PORT)"
	@echo "  using the MAIN backend :$(MAIN_BACKEND_PORT) and the shared database. Backend changes show up after merge."
	cd $(FRONTEND) && BACKEND_PORT=$(MAIN_BACKEND_PORT) npm run dev -- --host --port $(FRONTEND_PORT) --strictPort
else
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
endif

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
