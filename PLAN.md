# Studilo v1 — PLAN

This is the Phase 0 plan: what the audit confirmed, what we keep, port, or delete, and the target
layout. The detailed audit of the previous code base is in `docs/DEVIN-PIVOT-AUDIT.md` (2026-09-21).
Architecture trade-offs are in `DECISIONS.md`. Progress is in `CHANGELOG.md`.

## 1. Audit confirmation (2026-09-24)

Every row of the brief's audit table was checked against the working tree at `eff5d11`.

| # | Problem | Verdict | Evidence |
|---|---------|---------|----------|
| 1 | No real UI | CONFIRMED | Frontend is a separate Next.js repo (`../tutor-ia-frontend`) with login/register and an empty workspace page. Its typecheck fails (`cookies` missing on `Request` in the logout and refresh BFF routes). |
| 2 | UX never designed | CONFIRMED | No UX document. The flows in `../SDD-PLAN.md` are API-centric. |
| 3 | RabbitMQ workers, not agents | CONFIRMED | `pdf_worker_multi_queue.py` and `exam_worker.py` consume a queue and run a fixed pipeline. They have no tool loop. `ProfessorAgent` returns fixed text. |
| 4 | No end-to-end process | CONFIRMED | Upload → exam is not connected: the exam row is never persisted and the uploader identity is lost in vector metadata. |
| 5 | Poor parsing | CONFIRMED | Every PDF goes to Gemini OCR (paid) regardless of text layer. The file type comes from the extension. There is no legibility check. |
| 6 | RAG not scoped by user | CONFIRMED | Solver searches the shared `engineering_knowledge` Qdrant collection with no user/course filter. Vector payloads have no `user_id`. Upload accepts an arbitrary `course_id`. |
| 7 | Exams use fake data | CONFIRMED | Exam worker instantiates `MockPatternRepository`/`MockMasteryRepository`. The grader uses a "Mock temporal" question source. The golden test uses a fake exam id. |
| 8 | Status always `PROCESSING` | CONFIRMED — root cause in CHANGELOG | Hardcoded literal in `check_exam_status`, and no job row exists anywhere to read. |
| 9 | Auth broken | CONFIRMED | Three auth paths (Node service, Python gateway, Next BFF). Field names disagree (`first_name` vs `full_name`, `refresh_token` vs `refreshToken`). No logout or revocation exists. The Node service queries columns that do not exist. |
| 10 | Several languages | CONFIRMED | Python, JavaScript (Node auth + vectordb), SQL init scripts, Bash, PowerShell, Jinja HTML templates, TypeScript (separate repo). |
| 11 | Weak schema, embedded credentials | CONFIRMED | `init.sql`, ORM and the single Alembic revision disagree (the migration alters an `exams` table the SQL does not create). Credential literals appear in Python defaults, SQL and scripts. **Tracked `.env` files** hold provider keys and a JWT secret. |
| 12 | Disorganised structure | CONFIRMED | 3 RabbitMQ clients, 3 DB session factories, 2+ MinIO clients, 2 alternative FastAPI entrypoints, empty `k8s/` and `config/` placeholders. |
| 13 | No tool loop, no triggers | CONFIRMED | No tool-calling code and no scheduler. |

### Extra findings (added to the table)

| # | Finding | Action |
|---|---------|--------|
| A1 | `src/services/ai/.env`, `src/services/auth/.env` and `src/services/vectordb/.env` are **committed** and contain `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `COHERE_API_KEY`, `PINECONE_API_KEY`, `JWT_SECRET` and `DB_PASSWORD` entries. | Delete the files. **The owner should rotate those keys.** Removing them from history requires a history rewrite, which is destructive and waits for explicit owner approval. |
| A2 | Most repo directories were read-only (`dr-xr-xr-x`). | Owner write permission restored (`chmod -R u+w`) so the cleanup could run. |
| A3 | The working tree had pre-existing uncommitted changes (mostly CRLF plus 6 substantive auth/compose edits). | Preserved in `git stash` (`stash@{0}`, "pre-existing uncommitted changes before Studilo v1 pivot"). Work continues on branch `studilo-v1`. |
| A4 | `/health` reports `healthy` with the broker down. | The new health check actually queries the DB. |
| A5 | Solver prompt explicitly allows a general-knowledge fallback, so answers can be ungrounded. | The Exam agent must cite note sections, and `save_exam_pack` rejects uncited questions. |
| A6 | CI only checks folder names and Compose syntax. No tests run. | CI runs backend tests, frontend typecheck/build and gitleaks. |
| A7 | `CLAUDE.md`, `.cursor/rules/backend.mdc` and `../SDD-PLAN.md` prescribe Postgres + RabbitMQ + Phase-0-only. They contradict the v1 brief (SQLite, no RabbitMQ, full product). | This is an architecture contradiction, not a product one, so we follow the brief. The rule files are rewritten (see `DECISIONS.md` D-01). `../SDD-PLAN.md` is outside the repo and is marked superseded in the new `CLAUDE.md`. |

## 2. Keep / port / delete

The new code is written fresh under `backend/`. "Port" means an idea or algorithm is carried over and
rewritten against the new schema. No file is copied as-is, because every old module depends on the
Postgres/RabbitMQ/MinIO plumbing being removed.

| Old path | Decision | Why |
|----------|----------|-----|
| `src/shared/vectordb/chunker.py` | **Port** → `backend/app/ingestion/chunker.py` | LaTeX-aware paragraph splitting is sound. The rewrite adds hard-split of oversized paragraphs and tests. |
| `src/services/learning/logic/blueprint.py` | **Port (idea)** → Exam agent prompt | The difficulty/cognitive distribution becomes guidance in `prompts/exam_agent.md`. |
| `src/services/ai/prompts.py`, `solver/prompts.py` | **Port (ideas)** → `backend/prompts/` | The rigor rules (units, LaTeX, solvable data) go into the versioned prompts. |
| `src/services/learning/logic/study_planner.py` | **Delete** | A study plan is out of v1 scope. The Planner decides on triggers instead. |
| `src/services/learning/logic/{exam_generator,content_selector,style_selector,grader,priority_scorer,professor_agent}.py` | **Delete** | Built on mocks and broken DTOs. The Exam agent replaces them. |
| `src/services/learning/infrastructure/pdf_renderer.py` + templates | **Delete** | WeasyPrint needs system libraries (pango/cairo). PDF export is a print stylesheet in the browser instead (D-09). |
| `src/services/learning/workers/exam_worker.py`, `src/services/processor/**` | **Delete** | These are queue consumers, not agents. Replaced by the orchestrator plus agents. |
| `src/services/ai/service.py`, `ai/config.py`, `ai/schemas.py` | **Delete** | Hardcoded OpenAI model. Replaced by the provider layer driven by `models.yaml`. |
| `src/services/solver/**` | **Delete** | Unscoped RAG. Search is a user-scoped tool (`search_notes`). |
| `src/services/auth/**` (Node), `src/services/vectordb/**` (Node) | **Delete** | Removed language, broken or dead. |
| `src/api-gateway/**` | **Delete** | Replaced by `backend/app/api`. Its sync-SQLAlchemy/JWT auth is replaced by DB-backed sessions. |
| `src/main.py`, `src/api/`, `src/shared/**` (except chunker idea) | **Delete** | Duplicate entrypoints and clients. |
| `src/infrastructure/**` (Postgres HA, HAProxy, Redis, RabbitMQ, Prometheus/Grafana, Logstash, PowerShell/MinIO scripts) | **Delete** | Local-first v1 needs none of these (D-02, D-03). |
| `docker-compose.yml` (26 services), `requirements.txt`, `Makefile`, `.github/workflows/ci.yml` | **Delete / rewrite** | Replaced by `make dev` (D-17) and a real CI. |
| `tests/**` | **Delete** | They hit live services with fake ids. New tests live in `backend/tests`. `contexto_examen.pdf` is kept as a real-world text-PDF fixture. |
| `k8s/`, `config/`, `.vs/`, `docs/{api,architecture,runbooks}/.gitkeep` | **Delete** | Empty placeholders or IDE state. |
| Tracked `.env` files | **Delete** (see A1) | Secrets. |
| `../tutor-ia-frontend` (Next.js, separate repo) | **Not reused** | The brief requires React + Vite in the same monorepo. The sibling repo is left untouched on disk. |
| `docs/DEVIN-PIVOT-AUDIT.md` | **Keep** | Historical evidence. |

## 3. Target layout

```
.
├── PLAN.md  DECISIONS.md  UX.md  CHANGELOG.md  README.md  CLAUDE.md
├── Makefile                  # make setup | make dev | make test | make migrate | make secrets-scan
├── scripts/ensure_secret.py  # generates APP_SECRET_KEY on first setup
├── .env.example              # every key, empty values
├── backend/
│   ├── pyproject.toml, uv.lock, alembic.ini
│   ├── config/models.yaml    # task → provider/model, fallbacks, pricing (no secrets)
│   ├── prompts/              # versioned agent system prompts (*.md with version header)
│   ├── app/
│   │   ├── main.py           # FastAPI app + lifespan (starts orchestrator + scheduler)
│   │   ├── config/           # Settings (pydantic-settings), models.yaml loader/validator
│   │   ├── db/               # engine/session, ORM models, migrations/, scoped repository
│   │   ├── api/              # routers (auth, onboarding, courses, uploads, notes, memory, exams, activity, settings, inbox)
│   │   ├── auth/             # password hashing, sessions, current_user dependency
│   │   ├── llm/              # provider abstraction (openai-compatible, anthropic), cost logger, embeddings
│   │   ├── ingestion/        # magic bytes, legibility, OCR, router, chunker
│   │   ├── agents/           # base loop + planner, ingestion, notes, memory, exam
│   │   ├── tools/            # typed, user-scoped tools per agent
│   │   ├── orchestrator/     # events, DB-backed jobs, worker loop, scheduler/triggers, state machines
│   │   └── vectors.py        # sqlite-vec store, partitioned by user_id
│   └── tests/
├── frontend/                 # Vite + React + TS + Tailwind + TanStack Query + KaTeX
└── docs/
```

## 4. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| Phase 0 | Audit, this plan, cleanup, secrets + `models.yaml` + Settings, fixes for #6/#8/#9/#10/#11/#12 at the foundation level | Old tree gone; backend boots; startup key validation works |
| UX | `UX.md` | Screens, flows, empty/error states |
| M1 | Schema + Alembic, auth, user scoping, settings API, onboarding UI | Auth tests, isolation tests, onboarding in browser |
| M2 | Ingestion router + `ingestion_log` | Fixture tests for text / garbled / scanned / handwriting photo / equation page |
| M3 | LLM layer, agent loop, Notes agent, Subject screen | Notes agent merges incrementally with sources |
| M4 | Course Memory agent, orchestrator, triggers, Today + inbox | Trigger tests (class_ended, missed slot, upload_completed) |
| M5 | Exam agent, Exam Pack screen, exam triggers | T-14/7/3 tests; pack with ≥2 verified mock exams citing notes |
| M6 | Activity/Costs, Settings UI, polish, E2E | E2E journey test, isolation test across every endpoint and tool, gitleaks clean, `make dev` |
