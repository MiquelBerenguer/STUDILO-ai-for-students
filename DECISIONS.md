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
- One file (`data/studilo.db`) plus `data/uploads/<user_id>/…`. Zero services to run.
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
