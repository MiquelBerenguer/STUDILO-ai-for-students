# AGENTS.md: rules for every coding agent (Codex, Claude Code, Cursor, …)

Read **`CLAUDE.md`** first. It holds the architecture, the commands and the non-negotiable rules
(secrets only in `.env`, models only in `models.yaml`, user scoping, `transition()`, no mocks, Alembic
for schema changes, no fake agentic UI). Product decisions are in `DECISIONS.md`, screens in `UX.md`.
The product name comes from `config/brand.json`; never hardcode it.

Verify before you say you're done: `make test` (backend pytest + frontend typecheck/build) and
`cd backend && uv run ruff check app tests`.

---

## Parallel work: one view per worktree

Novi is built by several agents at once, each in its **own git worktree and branch**. Every view spans
backend and frontend. You **own** the files of your view. Everything else is **shared**: read it
freely, change it only as described below.

| Worktree / branch | View | You own (backend) | You own (frontend) |
|---|---|---|---|
| `ask-novi` → `feature/ask-novi` | **Ask Novi**: command bar, ⌘K, answers | `app/command/*`, `app/tools/qa.py`, `prompts/qa_agent.md`, the `answer_question` handler | `components/CommandBar.tsx` |
| `overview` → `feature/overview` | **Overview**: the Novi feed (home) | `app/api/routers/feed.py`, `app/orchestrator/cards.py`, `app/orchestrator/actions.py`, `app/agents/describe.py` | `pages/Feed.tsx`, `components/ActionCard.tsx`, `components/LiveRun.tsx`, `components/Layout.tsx` |
| `schedule` → `feature/schedule` | **Schedule**: timetable, onboarding, calendars | `app/onboarding/*`, `app/api/routers/onboarding.py`, `app/integrations/calendar_feed.py`, `app/api/routers/integrations.py` (calendar routes), slot routes in `app/api/routers/setup.py`, `app/agents/planner.py` | `pages/Schedule.tsx`, `pages/Onboarding.tsx`, `components/Timetable.tsx` |
| `exam-prep` → `feature/exam-prep` | **Exam prep**: exams, Exam Packs, practice | `app/api/routers/exams.py`, `app/tools/exam.py`, `prompts/exam_agent.md`, `prompts/exam_verifier.md`, the `build_exam_pack` handler, exam routes in `setup.py` | `pages/Exams.tsx`, `pages/ExamPack.tsx` |
| `courses` → `feature/courses` | **Courses**: notes, course memory, sources, uploads | `app/api/routers/notes.py`, `app/api/routers/uploads.py`, `app/tools/notes.py`, `app/tools/memory.py`, `app/tools/store.py`, `app/integrations/upc_guides.py`, `prompts/notes_agent.md`, `prompts/course_memory_agent.md`, `prompts/catch_up.md`, course routes in `setup.py` | `pages/Courses.tsx`, `pages/Subject.tsx`, `pages/Upload.tsx`, `components/editors.tsx` |

Tests: add your tests in a new file named after your view (e.g. `tests/test_schedule_view.py`). Only
edit an existing test file if your change breaks it.

### Shared hotspots: how to change them without conflicts
- **`app/db/models.py` + migrations.** Add columns or tables, never rename or remove existing ones.
  Use your **reserved migration id** so revisions never collide: `0005` schedule · `0006` courses ·
  `0007` exam-prep · `0008` overview · `0009` ask-novi. Set `down_revision = "0004"`. The integrator
  re-chains migrations at merge time.
- **`app/orchestrator/handlers.py`, `events.py`, `worker.py`**: add new functions, events or `HANDLERS`
  entries at the **end** of the relevant block. Don't reorder or reformat existing code.
- **`app/main.py`** (router registration), **`frontend/src/App.tsx`** (routes),
  **`frontend/src/types.ts`**, **`frontend/src/index.css`**, **`frontend/src/hooks.ts`**,
  **`frontend/src/api.ts`**: append only. Put new types in a new block at the end of `types.ts`,
  marked with your view name.
- **`config/models.yaml`, `app/config/models_config.py`**: a new model task needs a line in both. Add it
  at the end, never change other tasks' models.
- **`CHANGELOG.md`, `DECISIONS.md`, `UX.md`**: don't edit them in a view branch. Put the changelog
  lines and decisions in your final summary (or `worker_done`). The integrator writes them at merge
  time, which keeps these files conflict-free.
- Need to change a file another view owns? Ask first (Orca: `orca orchestration ask`), or describe the
  change in your summary for the integrator.

### Running the app in parallel
Each worktree has a gitignored `.worktree.mk` with its own ports, so every one can run `make dev` at
the same time. Each worktree also has its own `data/` (separate database and uploads).

| Worktree | Backend | Frontend |
|---|---|---|
| main checkout | 8000 | 5173 |
| ask-novi | 8001 | 5174 |
| overview | 8002 | 5175 |
| schedule | 8003 | 5176 |
| exam-prep | 8004 | 5177 |
| courses | 8005 | 5178 |

### Finishing
Commit on your branch with a clear message. Don't merge into `master` and don't push unless asked. The
integrator merges one view at a time: review, `make test`, merge, then the other branches rebase.
