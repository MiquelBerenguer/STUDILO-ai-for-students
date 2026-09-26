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

## Parallel worktrees
Novi is built by several agents at once, one view per worktree. **Read `AGENTS.md`** for which files
your view owns, the shared-file rules (reserved migration ids, append-only files) and your dev ports.

## Where things live (v2)
- Product name/tagline: `config/brand.json` only (D-20). Feature flags for UI stubs: `config/features.json`.
- Feed cards: `app/orchestrator/cards.py` (create only from triggers/jobs). Undo/approval:
  `app/orchestrator/actions.py`. Plain-language step labels: `app/agents/describe.py`.
- Command bar: `app/command/parse.py` (deterministic) + `app/command/service.py` (dispatch, JEV fallback).
- Onboarding: `app/onboarding/timetable.py` (pure parsers) + `app/onboarding/extract.py` (pipeline, trace).
- Frontend: `pages/Feed.tsx` (home), `components/{ActionCard,LiveRun,CommandBar,Timetable}.tsx`.
- UPC integrations: `app/integrations/calendar_feed.py` (encrypted calendar link, daily sync) and
  `app/integrations/upc_guides.py` (public course guides → syllabus). Secrets at rest: `app/auth/crypto.py`.
- UI screenshots: `scripts/ui_screens.py` (dev-only, Playwright + system Chrome).

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
- Never fake agentic UI: every card/run/step shown must come from a DB row; stubs only behind
  `config/features.json` flags and listed in `UX.md` §10.
- No mocks/fakes in production code. The scripted test provider lives only in `backend/tests/`.
- No silent `except`. Record the error (job/upload/pack state, trace step, llm_calls row).
- Agent prompts live in `backend/prompts/*.md` with a `version:` header. Bump it when you change a prompt.
