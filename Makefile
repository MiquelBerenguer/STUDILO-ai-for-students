.PHONY: help setup dev backend frontend test lint migrate check secrets-scan

BACKEND := backend
FRONTEND := frontend

help:
	@echo "make setup   - create .env (with APP_SECRET_KEY), install backend + frontend deps"
	@echo "make dev     - validate config, run backend :8000 and frontend :5173 (LAN-exposed)"
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
	@echo "Backend http://localhost:8000  ·  Frontend http://localhost:5173"
	@trap 'kill 0' INT TERM EXIT; \
	  (cd $(BACKEND) && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app) & \
	  (cd $(FRONTEND) && npm run dev -- --host) & \
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
