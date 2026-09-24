# Studilo v1

A local-first, multi-agent study assistant for engineering students. Studilo works like a second
student who follows the course with you:

1. You set up your subjects, weekly schedule, semester and exam dates.
2. When a class ends, Studilo asks for that class's notes (in-app inbox and browser notification).
3. You upload a PDF, phone photos, scans or typed text. A **deterministic-first router** reads them
   (text layer → local OCR → vision model only when needed).
4. Agents merge the content into structured **topic notes** (every section links to its source) and
   keep a living **course memory**: sessions, pace, topic dependencies, missed classes, open doubts.
5. At T-14, T-7 and T-3 days before each exam, the Exam agent builds an **Exam Pack**: a study guide
   and several verified practice exams with solutions and rubrics, all citing your notes.

## Quick start
Requirements: [uv](https://docs.astral.sh/uv/) and Node.js ≥ 20. uv installs Python 3.12 itself.

```bash
cp .env.example .env        # fill in the provider keys referenced by backend/config/models.yaml
make dev                    # installs deps, validates config, starts backend :8000 + frontend :5173
```
Open http://localhost:5173 and register. From a phone on the same Wi-Fi, open the LAN URL shown on
the Upload screen.

- `make test`: backend tests (pytest) + frontend typecheck and build.
- `make check`: validate `.env` + `models.yaml` without starting anything.
- A missing key fails fast, naming it:
  `OPENAI_API_KEY is not set (required by provider 'openai' for: exam_generation, …)`.

## Configuration
- **Secrets**: `.env` only (gitignored). See `.env.example` for every key.
- **Models**: `backend/config/models.yaml` maps each task (`jev_classification`, `vision_transcribe`,
  `notes_structuring`, `course_memory`, `exam_generation`, `exam_verification`, `embeddings`) to a
  provider/model with a fallback chain, plus per-model pricing for the cost log. Edit one line, or use
  Settings → Models, to switch a model. The file is hot-reloaded, so no restart is needed.
- Supported providers: `anthropic`, `openai`, `google`, `deepseek`, `openrouter`, `ollama` (local),
  and `fastembed`/`local` for embeddings.

## Architecture (short)
- **Backend** (`backend/`): FastAPI, SQLAlchemy 2 + Alembic, SQLite + sqlite-vec (vectors partitioned
  by user). Agents are plain Python classes with typed tools and a traced tool-calling loop.
  An in-process orchestrator runs DB-backed jobs and a scheduler tick (no broker).
- **Frontend** (`frontend/`): React + Vite + TypeScript + Tailwind + TanStack Query, with Markdown
  and KaTeX rendering.
- **Docs**: `PLAN.md` (audit, keep/port/delete, layout), `DECISIONS.md` (trade-offs), `UX.md`
  (screens and flows), `CHANGELOG.md` (milestones), `docs/DEVIN-PIVOT-AUDIT.md` (audit of the old code).
