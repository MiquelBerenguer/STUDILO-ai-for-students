# Architecture decisions

Each entry records the choice, the simpler/harder alternative, and the trade-off.

## D-01 — The v1 brief supersedes `SDD-PLAN.md`, `CLAUDE.md` and `.cursor/rules`
The old rule files prescribed Postgres, RabbitMQ, MinIO, Qdrant and a "cleanup-only" phase. The v1
brief prescribes local-first SQLite, agents and a full product. The product (students upload notes,
the system generates exams) is unchanged and extended, so this is an architecture change, not a
product contradiction. `CLAUDE.md` and `.cursor/rules/backend.mdc` are rewritten to match.

## D-02 — Remove RabbitMQ. Use a DB-backed job table with an in-process asyncio worker
- Local-first, single user machine, one process. A broker adds a service, credentials and a
  second source of truth for job state (the root cause of issue #8's family of bugs).
- `jobs` rows are the only job state. The UI reads them directly, so status cannot drift.
- Trade-off: no horizontal scaling of workers. With SQLite that is not a goal. If needed later, the
  `jobs` table can be consumed by N processes with `UPDATE … WHERE status='queued' … RETURNING`.
- APScheduler was not used: triggers are a 30-second asyncio tick that calls one pure function
  (`scheduler.tick(now)`). It is simpler, and tests can drive it with an injected clock.

## D-03 — SQLite + sqlite-vec instead of Postgres + Qdrant; local disk instead of MinIO
- One file (`data/app.db`) plus `data/uploads/<user_id>/…`. Zero services to run.
- Vectors live in a `vec0` virtual table with `user_id` as a **partition key**. The KNN query
  itself is constrained by user, so unscoped retrieval is impossible, not merely filtered afterwards.
- WAL mode plus a single writer worker keeps concurrency manageable.

## D-04 — Agents are plain Python classes; no agent framework
A base `ToolLoopAgent` (≈150 lines) does: system prompt from `prompts/`, typed tools (Pydantic
args → JSON schema), model call, tool execution, step limit, stop condition (`finish`-style tool or a
reply with no tool calls), and a full trace in `agent_runs`/`agent_steps`. LangGraph/CrewAI would
add dependency weight and hide the trace format we need for the Activity screen.

## D-05 — Deterministic agents where an LLM adds nothing
The **Ingestion agent** and the **Planner/Scheduler agent** use the same tool registry, scoping and
trace as the other agents, but their policy is code, not an LLM. This follows "deterministic
first": a typed PDF must cost zero LLM calls, and "class ended → ask for notes" does not need a
model. They escalate to LLMs only through specific tools (`vision_transcribe`, `classify_topic`).
The Notes, Course Memory and Exam agents are real LLM tool loops. The Course Memory agent also has
deterministic handlers for events that need no reasoning (flagging a missed session).

## D-06 — Auth: email + password (bcrypt) and DB-backed opaque sessions in an HttpOnly cookie
- Simpler than JWT access/refresh pairs and it supports real logout (row deletion).
- The cookie holds a random 256-bit token. The DB stores only its HMAC-SHA256 (keyed by
  `APP_SECRET_KEY`), so a leaked DB does not leak live sessions.
- `bcrypt` is used directly. `passlib` is unmaintained and breaks with bcrypt ≥ 4.1.

## D-07 — User scoping lives in one data-access class
`ScopedRepo(session, user_id)` is the only way routes and tools reach user data. Every query it
builds adds `WHERE user_id = :uid`, and every insert sets `user_id`. Tools receive a `ToolContext`
built by the orchestrator from the job's `user_id`. Tool argument schemas never contain a
`user_id` field, so a model cannot pass one.

## D-08 — LLM layer: raw `httpx`, two wire formats
OpenAI-compatible chat completions cover OpenAI, DeepSeek, OpenRouter, Ollama (`/v1`) and Google
(Gemini's OpenAI-compatible endpoint). Anthropic uses its Messages API. That is two adapters for six
providers, without adding six SDKs. LiteLLM was rejected: heavy transitive dependencies and a
second cost table that could disagree with `models.yaml`. Cost is always computed from the
`pricing` section of `models.yaml` and the provider-reported token usage.

## D-09 — PDF export via browser print stylesheet, not WeasyPrint
WeasyPrint needs pango/cairo/gdk-pixbuf system packages, which conflicts with "one command on a
fresh clone". The Exam Pack page has a print stylesheet, and "Export PDF" calls `window.print()`.
KaTeX renders identically in print. Trade-off: the user picks "Save as PDF" in the print dialog.

## D-10 — Local OCR: RapidOCR (PaddleOCR models on ONNX Runtime)
`rapidocr-onnxruntime` is a pip package with bundled models. It needs no system Tesseract, gives
per-line confidence, and handles Spanish/Catalan/English Latin text. Preprocessing (grayscale,
deskew via minAreaRect, CLAHE contrast) uses OpenCV-headless, which RapidOCR already depends on.

## D-11 — Legibility check uses `wordfreq` and `ftfy`
`wordfreq` provides the dictionary-word ratio for en/es/ca/fr/de without shipping word lists.
`ftfy.badness` detects mojibake (broken encoding). Other signals: chars per page, garbage ratio
(U+FFFD, private-use, control chars, `(cid:N)`).

## D-12 — Embeddings default to local `fastembed` (multilingual MiniLM, 384-d), hashing fallback
No API key is needed and the model downloads once (~220 MB) on first use. A built-in deterministic
`hashing` embedder (`local/hashing-384`) is the fallback when the model cannot be loaded (offline
first run), and tests use it. Vector tables are created per dimension (`vec_chunks_384`), so
switching the embedding model in `models.yaml` does not corrupt existing vectors. Re-embedding is a
separate maintenance command.

## D-13 — Topic assignment: embeddings first, JEV only in the ambiguous band
Cosine similarity to existing topic centroids: `≥ 0.80` maps directly, `< 0.45` means a new topic,
and the band in between asks the cheap model a closed question (`maps_to: Literal[ids…, "NEW"]`,
validated by Pydantic, one retry, then the safe default "NEW"). A new topic's title comes from the
first Markdown/heading-like line. The LLM is asked for a title (max 60 chars, validated) only when
none exists.

## D-14 — Notes are stored as sections, and the Notes agent cannot rewrite a note wholesale
`note_sections` rows (topic, position, heading, markdown) are linked to uploads through
`section_sources`. The agent's `update_topic_note` tool only supports `append_section` and
`revise_section` (one section, sources required). There is no "replace whole note" operation, so
incremental merging is enforced by the tool surface, not by prompt wording.

## D-15 — Default model mapping uses providers the owner already has keys for (Google, OpenAI)
The owner's pre-existing `.env` had Google and OpenAI keys, so the defaults use
`gemini-3.1-flash-lite` (cheap classification/vision), `gemini-3.5-flash` (notes/memory/verification)
and `gpt-5.6-terra` (exam generation), with cross-provider fallbacks. Switching to Anthropic,
DeepSeek, OpenRouter or Ollama is a one-line edit. Pricing was taken from the providers' public
pages on 2026-09-24 and should be checked periodically.

## D-16 — Frontend: Vite + React + TanStack Query + Tailwind v4, served through the Vite proxy
The Vite dev server proxies `/api` to FastAPI, so the cookie is same-origin and no CORS is needed.
`--host` exposes it on the LAN, which gives phone uploads for free (the Upload screen shows the
LAN URL as a QR code). Browser notifications use the Notification API from the inbox poller.

## D-17 — One-command start is `make dev`; no docker-compose in v1
Docker is not installed on the development machine, so a compose file could not be verified. Shipping
an untested one would break the "fresh clone works" promise. `make dev` needs only `uv` (which
installs Python 3.12) and Node ≥ 20. A compose file can be added once it can be tested.

## D-18 — Sync SQLAlchemy; each orchestrator job runs in its own thread + event loop
SQLite with sync SQLAlchemy is the simplest correct choice (sqlite-vec loads via the stdlib driver).
Agents are async (HTTP to LLMs), so every job runs `asyncio.run(...)` in a worker thread. A job
waiting on SQLite's single writer lock then blocks only its own thread (busy_timeout), never a shared
event loop where the lock holder could not make progress. Tools commit before slow steps (OCR, LLM,
embeddings), so write locks are held for milliseconds.

## D-19 — The domain term is "practice exam" (the brief's "mock exam")
Renamed in code, API and UI, so that `grep -i "mock|fake|dummy|lorem"` over production code is a
meaningful check. Any hit now means real placeholder data.

## D-20 — Product name lives in `config/brand.json`; internal identifiers are brand-neutral
- `config/brand.json` (`name`, `tagline`, `slug`) is the only place the product name is written. The
  backend reads it via `app/config/brand.py` (FastAPI title, startup messages, agent prompts through a
  `{brand}` placeholder, notification text). The frontend imports the same file (`frontend/src/brand.ts`),
  and a small Vite plugin injects it into `index.html` (`%BRAND_NAME%`).
- A JSON file rather than `brand.ts` + a Python constant: two constants would drift. JSON is readable
  natively by both languages.
- Internal identifiers were made **brand-neutral** instead of renamed to "novi", so the next rename
  does not touch them: cookie `session` (was `studilo_session`; renaming again would log everyone
  out), loggers use `__name__`, the default DB file is `data/app.db`, packages are `backend` /
  `frontend`, the DOM event is `app:unauthorized`.
- **Intentional leftovers of "studilo"** (not renamed, low value or risky):
  - git branch `studilo-v1` and the GitHub repo `STUDILO-ai-for-students`: renaming needs the owner
    (remote settings, open links).
  - the local folder path `…/Studilo/TUTOR-IA/…` on the owner's machine.
  - historical documents describing the past: `docs/DEVIN-PIVOT-AUDIT.md`, old `CHANGELOG.md`
    entries, and "(formerly Studilo)" notes in `PLAN.md`, `README.md`, `docs/SYSTEM_WALKTHROUGH.md`.
  - the owner's local, gitignored `.env` still has `DATABASE_URL=sqlite:///./data/studilo.db`. It keeps
    working; not edited because `.env` holds secrets and is the owner's file.
- Changing the tagline or name: edit `config/brand.json`, rebuild the frontend. Prompts pick it up on the
  next run.

## D-21 — The design reference is committed
`design/reference/` (Figma Make export, ~190 KB without `node_modules`) is small, so it is committed for
future comparison; its `node_modules/` is gitignored. It is reference material only: nothing imports it.

## D-22 — Feed cards reuse the `notifications` table
A card is a notification with typed actions, a status and a priority. One table serves both the feed
and the bell, so no two sources can disagree. Migration 0002 adds `status`, `actions`, `priority`,
`dedupe_key` (unique per user: a question is never asked twice), `action_id` and `course_id`. v1 rows
migrate as `open`/`done` from `read_at`.

## D-23 — Undo = per-job effect snapshots, not event sourcing
- Autonomous jobs record what they changed in `agent_actions.effects`:
  - sections created;
  - sections revised, with their previous heading, content and version;
  - topics created;
  - dependencies created;
  - the class-session and course-memory snapshot taken before the upload.
- Undo applies the inverse and marks the upload `undone`.
- Undo is **refused** (HTTP 409, with the reason) when later work depends on the change, e.g. a section
  created by the upload was revised again. Silently clobbering later work would be worse than saying no.
- The window is 7 days.
- Discarded alternative: full event sourcing (every write replayable). Much larger change, and not needed
  for "undo the last autonomous thing".

## D-24 — Approval only for Novi-initiated, high-impact actions
The policy is fixed in code (`actions.AUTONOMY_POLICY`), shown read-only in the feed:
- **Auto:** filing notes, course memory, missed-class flags, pack refreshes.
- **Asks first:** exam date/scope changes, deletion.

Deletions the student does themselves in secondary views stay direct: they are the student's own
action, not Novi's. The reference's "Autonomy mode" toggle is not implemented, because a toggle
without behaviour would be fake (flag `autonomy_toggle`, UX §10).

## D-25 — Live runs by 1 s polling, not SSE/WebSockets
`AgentTrace` already commits after every step. The feed polls every 1 s only while a run is `running`
(5 s otherwise); a job's runs poll until no run is active. With sync SQLite and a threaded worker, SSE
would add a fan-out layer for no visible difference at this scale. Revisit if many concurrent users.

## D-26 — Command bar: deterministic parser first, closed-intent JEV fallback, no chat
- Intents, dates (EN/ES/CA), durations and fuzzy course/exam matching are parsed with rules
  (`app/command/parse.py`, unit-tested).
- Only when no rule matches, the cheap model answers a closed question: an `IntentGuess` with a
  `Literal` intent and typed slots, one retry.
- Missing slots produce clarification chips instead of guesses.
- Every command is stored as an `Event(type="command")`.
- Results render as cards and live runs, not as a transcript.
- The reference's canned-reply chat was removed on purpose.

## D-27 — Guest users instead of pre-account storage
Onboarding step 1 creates a real user with `email = NULL`:
- scoping, cost logging and traces work unchanged;
- the account is claimed later (`POST /auth/claim`, same user id, data kept);
- guest creation is rate-limited per IP (20/h) and extraction per user (30/h), in memory
  (single-process, local-first);
- logging out as a guest warns that data would be lost.

Discarded alternative: holding the extraction client-side until registration. That makes LLM calls
unattributable (cost log needs a user) and loses work on reload.

## D-28 — Timetable extraction runs inside the request, traced as the `onboarding` agent
Time-to-first-value matters more than uniformity with the job queue:
- the grid path takes ~1–3 s (local OCR); vision takes ~5–10 s;
- the request returns the preview directly;
- the UI polls `/runs/live` meanwhile to stream the agent's steps.

If extraction ever becomes slow, it can move to a job without UI changes.

## D-29 — Grid parser: coloured blocks first, text clusters as fallback, escalate below 0.75
- Tokens come from the PDF text layer (exact) or RapidOCR boxes.
- The parser finds:
  - the weekday header row (EN/ES/CA names, ≥2 in order);
  - columns (midpoints between headers);
  - time labels left of the grid, forming a y→time mapping. Two hypotheses (labels on row lines vs
    centred in rows) are tested against the block edges.
- Cells come from saturated colour blocks (OpenCV). Otherwise vertical text clusters are used, with
  lower time confidence.
- Confidence combines token coverage, header and label counts, overlaps and unreadable cells. Below
  `GRID_ACCEPT = 0.75` the cheap vision task `timetable_extraction` runs.
- The angled phone photo fixture intentionally escalates: perspective breaks column geometry, and
  that is exactly the case vision is for.
- Pure functions in `app/onboarding/timetable.py`.

## D-30 — New model tasks: `course_qa`, `timetable_extraction`; the catch-up reuses `course_memory`
- `course_qa` (Q&A agent) uses the mid model like `course_memory`.
- `timetable_extraction` uses the cheapest vision model with a fallback.
- The missed-class catch-up is one structured call on `course_memory`: same context, same cost class.
- All three are in `models.yaml`, so swapping them is one line.

## D-31 — Progressive disclosure replaces onboarding fields
Onboarding no longer asks for semester dates, exams or syllabus; the Planner already treats missing
semester dates as unbounded. Instead, cards ask at the moment they matter:
- exam date → after the subject's first `class_ended`;
- past exams → when an exam is created;
- syllabus → after the first notes are filed;
- backfill notes → at confirm.

`/me/complete-onboarding` (v1) still exists; the new path is `/onboarding/confirm`.

## D-32 — Stubs behind `config/features.json`
Shared by both sides like the brand file (`GET /meta`). The reference's "Novi learned" card, readiness
ring and autonomy toggle have no backend, so their flags default to `false` and nothing renders.

## D-33 — v1 screens restyled by remapping Tailwind scales onto the reference palette
The reference tokens are added as-is in `@theme`. Tailwind's `indigo-*` and `slate-*` scales are
remapped to the reference primary/ink/muted/line colours. Subject, Exam Pack, Activity and Settings
adopt the look without rewrites. New screens use the tokens directly.

## D-34 — UI screenshots with Playwright + system Chrome, as a dev-only script
`scripts/ui_screens.py` walks the before/after flows and measures landing → feed time. It runs through
`uv run --no-project --with playwright`, so Playwright is not a product dependency. It uses
`channel="chrome"` to avoid downloading browsers.
