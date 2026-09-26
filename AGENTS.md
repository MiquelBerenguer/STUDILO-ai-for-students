# AGENTS.md: rules for every coding agent (Codex, Claude Code, Cursor, …)

Read **`CLAUDE.md`** first. It holds the architecture, the commands and the non-negotiable rules
(secrets only in `.env`, models only in `models.yaml`, user scoping, `transition()`, no mocks, Alembic
for schema changes, no fake agentic UI). Product decisions are in `DECISIONS.md`, screens in `UX.md`,
the current system in `docs/SYSTEM_WALKTHROUGH.md` (v1) and `CHANGELOG.md` (v2+). The product name comes
from `config/brand.json`; never hardcode it.

Verify before you say you're done: `make test` (backend pytest + frontend typecheck/build) and
`cd backend && uv run ruff check app tests`.

---

## How the five view agents work together

Novi is **one system**: one database, one backend, one app. Four agents finish it in parallel, one per
view. Each agent works in its **own git worktree** (a ~6 MB copy of the code on its own branch), so a
half-finished change never breaks another agent. Everything heavy is shared:

- **Database and files:** one shared database (the main checkout's `data/`). Worktree `.env` files
  point there.
- **Background engine:** runs only in the main checkout.
- **Running app:** only the main checkout runs the backend.
  - `make dev` **inside a worktree** starts only *your branch's frontend*, on your own port, against the
    main backend (it must be running: `make dev` in the main checkout).
  - Your **backend** changes are checked by your tests and show up in the app after merge.
- **Tests** always use a throwaway database and no API keys (`tests/conftest.py`), so they never touch
  the shared data and never spend money. Test AI behaviour with the scripted provider in `tests/fakes.py`.
- **Dependencies:** `frontend/node_modules` is a link to the main checkout's; Python packages come from
  `uv`'s shared cache. **Don't add or upgrade dependencies.** If you need one, say so in your summary.
- **Paid AI:** the preview talks to the real backend, which has real API keys. Don't trigger AI features
  (Ask Novi questions, exam builds, photo uploads) repeatedly while testing the UI.

| Worktree folder (`Studilo/novi-worktrees/…`) | Branch | View | Frontend preview |
|---|---|---|---|
| `ask-novi` | `feature/ask-novi` | **Ask Novi**: command bar, ⌘K, answers | http://localhost:5174 |
| `overview` | `feature/overview` | **Overview**: the Novi feed (home) + app shell | http://localhost:5175 |
| `schedule` | `feature/schedule` | **Schedule**: timetable, onboarding, calendars, triggers | http://localhost:5176 |
| `courses` | `feature/courses` | **Courses**: notes, course memory, sources, uploads | http://localhost:5178 |

The main checkout's app is http://localhost:5173 (backend 8000).

### Who owns what

You **own** your view's files: change them freely. Everything else is **shared**: read it, and change it
only under the rules in the next section. Ready-to-use briefs for each agent live in `docs/agents/`.

| View | Backend you own | Frontend you own |
|---|---|---|
| Ask Novi | `app/command/*`, `app/tools/qa.py`, `prompts/qa_agent.md`, handler `handle_answer_question` | `components/CommandBar.tsx` |
| Overview | `app/api/routers/feed.py`, `app/orchestrator/cards.py`, `app/orchestrator/actions.py`, `app/agents/describe.py`, `app/api/routers/activity.py`, `app/api/routers/settings.py`, `app/api/routers/auth.py` | `pages/Feed.tsx`, `pages/Activity.tsx`, `pages/Settings.tsx`, `pages/Auth.tsx`, `components/ActionCard.tsx`, `components/LiveRun.tsx`, `components/Layout.tsx`, `components/icons.tsx` |
| Schedule | `app/onboarding/*`, `app/api/routers/onboarding.py`, `app/integrations/calendar_feed.py`, calendar routes in `app/api/routers/integrations.py`, slot/profile routes in `app/api/routers/setup.py`, `app/agents/planner.py`, `app/tools/planner.py`, handlers `handle_class_ended`, `handle_check_missed`, `handle_missed_upload`, `handle_sync_calendar` | `pages/Schedule.tsx`, `pages/Onboarding.tsx`, `components/Timetable.tsx` |
| Courses | `app/api/routers/notes.py`, `app/api/routers/uploads.py`, `app/tools/notes.py`, `app/tools/memory.py`, `app/tools/store.py`, `app/tools/ingestion.py`, `app/ingestion/*`, `app/agents/ingestion.py`, `app/integrations/upc_guides.py` + guide route, `prompts/notes_agent.md`, `prompts/course_memory_agent.md`, `prompts/catch_up.md`, `prompts/vision_transcribe.md`, course routes in `setup.py`, handlers `handle_process_upload`, `handle_catch_up` | `pages/Courses.tsx`, `pages/Subject.tsx`, `pages/Upload.tsx`, `components/editors.tsx` |

**No Exam prep view.** There is no Exam prep agent or view any more. The exam backend keeps working (Exam
Packs at T-14/7/3, practice exams, focused exams from Ask Novi). Its files have **no owner and are frozen for
view agents**: `app/api/routers/exams.py`, `app/tools/exam.py`, the exam prompts, exam/assignment routes in
`setup.py`, `handle_build_exam_pack`, `pages/Exams.tsx` and `pages/ExamPack.tsx`. A view may *read* exams,
packs and assignments through the existing endpoints (e.g. Overview showing upcoming exams). If it needs a
change there, describe it in the summary for the integrator.

Tests: put yours in a new file named after your view (`tests/test_view_<view>.py`). Only edit an existing
test file if your change breaks it.

### Shared files: how to change them without conflicts
- **`app/db/models.py` + migrations.** The schema is shared by all views and the one database.
  - Add columns or tables only; never rename or remove.
  - Use your **reserved migration id**: `0005` schedule · `0006` courses · `0008` overview ·
    `0009` ask-novi (`0007` is unused), with `down_revision = "0004"`. The integrator re-chains them at
    merge time.
  - Never run a migration against the shared database: the main app applies it after merge.
- **`app/orchestrator/handlers.py`**: edit only the handler functions your view owns (table above). New
  handlers and new `HANDLERS` entries go at the **end**. Same for `events.py` (append event types).
- **Append-only files.** Add at the end, marked with your view name; don't reorder or reformat:
  - backend: `app/main.py` (routers);
  - frontend: `src/App.tsx` (routes), `src/types.ts`, `src/hooks.ts`, `src/api.ts`, `src/index.css`,
    `components/ui.tsx`.
- **`config/models.yaml` + `app/config/models_config.py`**: a new AI task needs a line in both, at the
  end. Never change another task's model.
- **`CHANGELOG.md`, `DECISIONS.md`, `UX.md`, `AGENTS.md`**: don't edit them in a view branch. Put your
  changelog lines, decisions and UX notes in your final summary; the integrator writes them at merge.
- **Need a file another view owns?** Don't edit it. Describe the change in your summary (or ask via Orca:
  `orca orchestration ask`), and the integrator coordinates.

### Finishing a piece of work
Work in small, complete increments. After each one:
1. `make test` passes and ruff is clean.
2. Commit on your branch with a clear message. Don't merge into `master` and don't push.
3. Tell the user what changed, with changelog lines, decisions, anything you need from another view, and
   how to see it (your preview URL).

The integrator merges one view at a time (review, `make test`, merge, restart the main app). The other
branches then pick up `master` with `git merge master`.
