# Changelog

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
