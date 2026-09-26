# Brief: Courses (notes, course memory, sources, uploads)

**Your worktree:** `novi-worktrees/courses` · **Branch:** `feature/courses` ·
**Preview:** http://localhost:5178 (`make dev` here; the main app must be running)

## The goal
Each course is the student's second brain for that subject:
- clean topic notes built from their own uploads, with every section linked to its source;
- a living course memory: what was covered when, the pace against the syllabus, open questions, missed
  classes.

Uploading should be effortless, and reading should be pleasant, maths included.

## Where it stands (read the code to confirm)
- Ingestion router, deterministic first: text layer → local OCR → vision only when needed (`app/ingestion/*`,
  `app/tools/ingestion.py`, `app/agents/ingestion.py`).
- The Notes agent and the Course memory agent run in `handle_process_upload`, with undo via
  `actions.py`. The catch-up job is in `handle_catch_up`.
- The syllabus can be imported from the public UPC course guide (`app/integrations/upc_guides.py`).
- Pages: `pages/Courses.tsx` (list), `pages/Subject.tsx` (notes, memory, sources) and
  `pages/Upload.tsx` (bulk upload, QR for phone). Subject and Upload still have the v1 layout,
  restyled only by the colour remap.

## What "finished" means
1. **Course page** in the reference style:
   - topics sidebar and a readable note view (KaTeX), with source chips opening the original file;
   - a course memory timeline (sessions, pace vs syllabus, missed classes, open questions to resolve);
   - the syllabus with "fetch from course guide".
2. **Editing with control:** edit or merge sections and rename or merge topics. Show section history
   where it exists. Deleting content Novi created needs a confirm; Novi-initiated deletions need an
   approval card (UX.md §7).
3. **Search** inside a course and across courses, using the existing vector search, which is already
   scoped by user.
4. **Uploads:** one clear flow (drop, camera, QR), live progress with the agent steps, retry, and a
   clear distinction between notes and past exams.
5. **Course settings:** name, colour, professor. Deleting a course must also delete its files and
   vectors (C-6).
6. **Known bugs in your area** (`docs/SYSTEM_WALKTHROUGH.md` Appendix C; line numbers are from v1):
   - **C-1:** past-exam uploads mark a class session as uploaded.
   - **C-5:** long uploads are truncated at 30,000 characters for the Notes agent. Process them in parts.
   - **C-6:** deleting a course leaves orphaned files and vectors.
   - **C-7:** chunk ids can be reused.
   - **C-10:** retrying a partly processed upload duplicates notes.
   - **C-11:** `reindex_section` can leave a section without chunks.
   - **C-12:** upload job progress isn't updated.
   - **C-14:** missing tests for the empty-OCR / no-text / JEV-title ingestion paths.
7. Tests in `tests/test_view_courses.py`, using the fixture factory (`tests/fixture_factory.py`) and the
   scripted provider.

## Boundaries
- You own:
  - backend: `app/api/routers/notes.py`, `app/api/routers/uploads.py`, `app/tools/notes.py`,
    `app/tools/memory.py`, `app/tools/store.py`, `app/tools/ingestion.py`, `app/ingestion/*`,
    `app/agents/ingestion.py`, `app/integrations/upc_guides.py` plus its route, and handlers
    `handle_process_upload`, `handle_catch_up`;
  - prompts: notes, course memory, catch-up and vision (bump `version:` when you change them);
  - course routes in `setup.py`;
  - frontend: `pages/Courses.tsx`, `pages/Subject.tsx`, `pages/Upload.tsx`, `components/editors.tsx`.
- `app/tools/store.py` is also used by the Exam agent and Q&A (search, read sections). Keep its function
  signatures compatible.
- Undo depends on the effect snapshots recorded in `handle_process_upload` (`app/orchestrator/actions.py`,
  Overview's). If you change how notes are written, keep `tests/test_feed_and_cards.py::test_undo_*`
  passing.
- Reserved migration id: `0006`.
