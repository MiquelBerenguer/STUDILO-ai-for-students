# Changelog

## v2.1 — First UPC integrations: connected calendar + course guides (2026-09-26)
These are the two items marked **GO** in `docs/research/UPC_INTEGRATION.md`. Neither needs a password
or an agreement with UPC.
- **Connected calendars** (`app/integrations/calendar_feed.py`):
  - The student pastes their Atenea/Moodle calendar export link, from a card after onboarding or from
    Schedule → Connected calendars.
  - The link carries a bearer token, so it is stored **encrypted** (Fernet, key derived from
    `APP_SECRET_KEY`) and never returned or logged.
  - A deterministic `calendar` agent re-reads the link daily (Planner trigger) and turns due/close
    events into assignments and exam events into exams, idempotent on the iCal UID.
  - New deadlines within 14 days become `deadline` cards (Mark done / Open course).
  - Unmatched events are counted, with examples.
  - A failed refresh becomes a single card that clears on the next success.
  - The fetch is SSRF-guarded.
- **UPC course guides** (`app/integrations/upc_guides.py`):
  - Given a subject code, Novi downloads the public guide PDF (upc.edu only) and fills the course
    syllabus from its CONTINGUTS/CONTENIDOS/CONTENTS section, with workload and page lines removed.
  - Available from the syllabus card and from Courses.
  - Checked against three real public guides, including EETAC 300021.
- Migration `0004` (`calendar_feeds`, `external_uid` on assignments/exams, `assignments.due_at`). New
  dependency: `cryptography`.
- 107 backend tests (9 new, no network: fetchers are monkeypatched).

## v2 — Novi: agentic feed, 3-step onboarding, rename (2026-09-26)
- **Rename to Novi** from one constant, `config/brand.json`, shared by backend and frontend. Internal
  identifiers are brand-neutral (D-20).
- **Novi feed is the home screen**:
  - **Needs you**: action cards with one-tap actions and inline inputs.
  - **Working now**: live agent runs with plain-language steps (`app/agents/describe.py`), expandable
    to the full trace.
  - **Since you were away**: runs finished since the last visit.
  - **Next up**: planned work computed from real schedules and exam thresholds.
  - Visual language from the design reference (`design/reference/`).
- **Cards** (`app/orchestrator/cards.py`), created only by triggers and jobs:
  - class-end upload prompt, missed class with "Catch me up" (new `catch_up` job), notes filed, Exam
    Pack refreshed;
  - progressive questions: exam date after a subject's first class, past exams, syllabus, backfill;
  - approval, answer, job failed with Retry, account claim.
- **Autonomy with control** (`app/orchestrator/actions.py`, table `agent_actions`):
  - autonomous changes record a snapshot and get a real 7-day Undo (notes filing, pack builds);
  - Undo is refused when later work depends on the change;
  - high-impact changes (exam date) are proposals that change nothing until approved.
- **Command bar** (hero + ⌘K):
  - deterministic parser first (EN/ES/CA dates, durations, fuzzy course matching), then a typed JEV
    fallback;
  - intents: generate exam (focus + duration), ask about course content (new **Q&A agent**,
    `course_qa` task), change exam date (approval), open.
- **Onboarding in 3 steps, no registration wall**:
  - a guest session is created when the timetable is dropped, and the account is claimed later from
    a card;
  - timetables are read from a screenshot, photo, PDF, `.ics` file or link, or pasted text:
    deterministic first (grid parser over PDF text or local OCR boxes, `.ics`, line regex), then the
    cheap vision model (`timetable_extraction`), then typed validation;
  - an editable week preview highlights low-confidence fields.
- Migrations `0002` (cards, agent actions, guest users, last-seen) and `0003` (course professor).
- **Research**: `docs/research/UPC_INTEGRATION.md` (go for calendar link + public guides; no-go for
  automatic Atenea login without a UPC agreement).
- **Verified**:
  - 98 backend tests, lint clean, frontend typecheck and build;
  - the 3-step E2E test (fresh user → feed, < 60 s);
  - the real UI took 2.3–2.5 s from landing to the Novi feed with a timetable screenshot, measured by
    `scripts/ui_screens.py`;
  - the new LLM paths (Q&A, catch-up, vision timetable fallback, focused exams) ran only against the
    scripted test provider, not a paid model.

## M6 — Activity/Costs, Settings, polish, verification (2026-09-24)
- Activity screen: cost/LLM-call/deterministic-step summary, cost by task, calls by model, ingestion
  paths, agent runs with full step traces, LLM call log (fallbacks, failures, unpriced models).
- Settings: provider status with masked keys and a free "Test connection" (lists models), a task →
  model editor that writes back to `models.yaml` (comments kept; rejects providers whose key is
  missing), and a Simulate panel that emits the same events as the automatic triggers.
- Security: uploaded files are served with the magic-byte media type, `nosniff` and a strict CSP
  (no stored XSS via `evil.html`).
- Orchestrator jobs run in their own thread/event loop (D-18). "Mock exam" renamed to "practice exam" (D-19).
- Verified: 49 backend tests, frontend typecheck + build, gitleaks clean from the pivot onwards,
  fail-fast startup naming the missing key, all 12 configured model IDs exist at their providers.

## M5 — Exam agent, Exam Pack screen, exam triggers
- Exam agent (LLM tool loop): `get_exam_scope`, `search_notes`, `read_sections`, `get_past_exams`,
  `add_study_guide_section`, `draft_question`, `verify_question` (separate verifier model: solvable /
  units / supported by cited notes), `save_exam_pack` (refuses incomplete or unverified packs).
- Scheduler emits `exam_approaching` at T-14/T-7/T-3, once per threshold. Each build is a new pack
  version that includes notes changed since the last build.
- Exam Pack screen: study guide with source links, practice exams, timed mode with auto-submit, solutions
  and rubric revealed after submission, self-scoring, print-to-PDF (D-09).

## M4 — Course Memory agent, orchestrator, triggers, Today + inbox
- DB-backed `events` → `jobs` orchestration with in-process workers and a scheduler tick (D-02).
- Planner agent (deterministic): `class_ended` when a slot ends (semester + timezone aware),
  `class_slot_passed_without_upload` after N hours.
- Course Memory agent: session summaries, pace (computed deterministically, described by the LLM),
  topic dependencies and open questions. Missed sessions are flagged by a deterministic handler.
- Today screen, inbox, and browser notifications.

## M3 — LLM layer, agent loop, Notes agent, Subject screen
- One LLM client for 6 providers (2 wire formats), fallback chains, and per-call cost/latency logging.
- `ToolLoopAgent`: typed Pydantic tools, step limit, stop condition, full trace in `agent_runs`/`agent_steps`.
- Notes agent merges incrementally (append / revise one section only, sources required). A
  deterministic fallback keeps the content if the agent fails.
- Subject screen: topic tree, KaTeX notes with source chips, memory timeline, sources.

## M2 — Ingestion router
- Magic-byte detection. PyMuPDF text layer with a legibility check (chars/page, garbage ratio,
  dictionary ratio via wordfreq, mojibake via ftfy). RapidOCR with deskew + CLAHE and confidence,
  equation, handwriting and diagram metrics. Escalation to the cheapest vision model only when needed.
- Topic assignment: embeddings first, JEV closed-choice (`maps_to: Literal[...]`) only in the
  ambiguous band, one retry, then a safe default.
- Every decision recorded in `ingestion_log` (path, scores, model, tokens, cost, latency).
- Fixture tests: text PDF, real text PDF, garbled PDF, scanned PDF, handwriting photo, equation
  page, clean photo, vision outage.

## M1 — Schema, auth, user scoping, settings/model config, onboarding UI
- Alembic migration `0001` (SQLite + sqlite-vec `vec0` partitioned by `user_id`).
- User scoping enforced in the session (`with_loader_criteria` on reads, owner check on flush).
- Email/password auth (bcrypt) with revocable DB sessions in an HttpOnly cookie. All non-public
  endpoints require auth (tested by enumerating the OpenAPI schema).
- Typed `Settings`, `models.yaml` store with hot reload, fail-fast key validation.
- Onboarding wizard: subjects → weekly schedule → semester dates → exam dates.

## Phase 0 — Audit and cleanup (2026-09-24)

### Root cause of issue #8, "status endpoint always returns PROCESSING" (recorded before the fix)
There are two independent causes, and fixing either one alone would not have been enough:

1. **Hardcoded value.** `src/services/learning/api/routes.py`, `check_exam_status()`, returned the
   literal `{"status": "PROCESSING", "download_url": None}` for any `task_id`, without reading anything.
2. **No real job data existed to read.** `request_exam_generation()` published a RabbitMQ message and
   returned `QUEUED` without inserting any row. `exam_worker.py` wrote the PDF to MinIO, then only
   logged success. On failure it logged and swallowed the exception. No component ever recorded
   `completed`/`failed`, and the only durable trace (the MinIO object) had no link to the `task_id`.
   The PDF pipeline had the same defect: the processor wrote a Redis status the active worker never
   updated, on a queue the worker did not consume.

Fix (Phase 0/M4): job state is a `jobs` row written by the orchestrator in the same process that runs
the work. The state machine is `queued → running → succeeded | failed`, and domain entities
(uploads, exam packs) have their own explicit state machines. Status endpoints read those rows.
Tests assert the state progression.

### Other changes
- Confirmed and extended the audit (`PLAN.md` §1, findings A1–A7).
- Pre-existing uncommitted changes preserved in `git stash@{0}`. Work continues on branch `studilo-v1`.
- Removed the Node services, RabbitMQ/Redis/Postgres-HA/monitoring infra, duplicated clients, mock
  repositories and tracked `.env` files.
- Secret scan of the **pre-pivot** history finds a Google API key in `check_models.py` (commit
  `336f7132`, Dec 2025; not the key currently in `.env`) plus the committed service `.env` files. Rotate
  them. Rewriting history is left to the owner.
