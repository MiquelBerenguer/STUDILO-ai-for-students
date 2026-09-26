# Novi v1 — agent context

Local-first, multi-agent study assistant for engineering students. Monorepo: `backend/` (Python),
`frontend/` (TypeScript). Read `PLAN.md` (layout, keep/port/delete), `DECISIONS.md` (architecture
trade-offs), `UX.md` (screens) and `CHANGELOG.md` before changing architecture.

`../SDD-PLAN.md`, `../CLAUDE.md` and `../ARCHITECTURE-AUDIT.md` describe the **old** Postgres/RabbitMQ
system and are superseded (DECISIONS D-01). Do not follow them.

## Commands
```bash
make setup      # .env from .env.example (+ APP_SECRET_KEY), uv sync, npm install
make dev        # validate config → backend :8000 (migrations on start) + frontend :5173 (LAN-exposed)
make test       # backend pytest + frontend typecheck/build
make lint       # ruff + tsc
cd backend && uv run pytest -q                   # backend tests only
cd backend && uv run alembic revision --autogenerate -m "msg"   # schema change → migration
cd backend && uv run python -m app.startup       # validate .env + models.yaml
```

## Rules
- Two languages only: Python 3.11+ (backend) and TypeScript (frontend).
- Secrets only in `.env` (gitignored; template `.env.example`). Model choices only in
  `backend/config/models.yaml`. Never hardcode keys or model names in code. Never log or return keys;
  use `mask_secret`.
- User scoping: routes and tools use the user-scoped session (`get_db` / `ToolContext.db`). Scoping is
  enforced by `app/db/engine.py`. Never add `user_id` to tool argument schemas. Vector search goes
  through `app/vectors.py` (partitioned by user).
- Every state change goes through `app/orchestrator/state_machines.py::transition`.
- Deterministic first: LLM calls go through `LLMClient` (cost-logged). Escalations must be logged
  (ingestion_log / agent trace) with their reason.
- Schema changes need an Alembic migration (`backend/app/db/migrations`).
- No mocks/fakes in production code. The scripted test provider lives only in `backend/tests/`.
- No silent `except`. Record the error (job/upload/pack state, trace step, llm_calls row).
- Agent prompts live in `backend/prompts/*.md` with a `version:` header. Bump it when you change a prompt.
