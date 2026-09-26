# Novi

> Provisional product name. It is defined once in `config/brand.json` (shared by backend and frontend);
> change it there. Formerly called Studilo.

A local-first, multi-agent study assistant for engineering students. Novi works like a second
student who does the organising and asks for your approval:

1. **Drop your timetable** (screenshot, photo, PDF, `.ics` link or pasted text). Novi reads it (no AI
   when the grid is clear), you confirm the week with one tap, and you land on the Novi feed. There is
   no registration wall: save the account later.
2. When a class ends, a card asks for that class's notes. Exam dates, past exams and the syllabus are
   asked for later, when they become relevant.
3. Uploads go through a **deterministic-first router** (text layer → local OCR → vision model only when
   needed). Agents file the content into **topic notes** with sources and keep a **course memory**.
   You can watch every step live and undo anything Novi did on its own.
4. At T-14, T-7 and T-3 days before each exam, the Exam agent builds an **Exam Pack**: a study guide and
   verified practice exams citing your notes.
5. The **command bar** (⌘K) handles requests like "make me a 1h exam on entropy", "what did we cover
   last week in Fluids?" and "move my Thermo exam to the 15th". High-impact changes wait for your
   approval.

## Quick start
Requirements: [uv](https://docs.astral.sh/uv/) and Node.js ≥ 20. uv installs Python 3.12 itself.

```bash
cp .env.example .env        # fill in the provider keys referenced by backend/config/models.yaml
make dev                    # installs deps, validates config, starts backend :8000 + frontend :5173
```
Open http://localhost:5173 and drop your timetable. From a phone on the same Wi-Fi, open the LAN URL shown on
the Upload screen.

- `make test`: backend tests (pytest) + frontend typecheck and build.
- `make check`: validate `.env` + `models.yaml` without starting anything.
- A missing key fails fast, naming it:
  `OPENAI_API_KEY is not set (required by provider 'openai' for: exam_generation, …)`.

## Configuration
- **Secrets**: `.env` only (gitignored). See `.env.example` for every key.
- **Models**: `backend/config/models.yaml` maps each task (`jev_classification`, `vision_transcribe`,
  `notes_structuring`, `course_memory`, `exam_generation`, `exam_verification`, `course_qa`,
  `timetable_extraction`, `embeddings`) to a
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
- **Docs**: `docs/research/UPC_INTEGRATION.md` (university integration research), `PLAN.md` (audit, keep/port/delete, layout), `DECISIONS.md` (trade-offs), `UX.md`
  (screens and flows), `CHANGELOG.md` (milestones), `docs/DEVIN-PIVOT-AUDIT.md` (audit of the old code).
