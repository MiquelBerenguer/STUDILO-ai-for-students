# Brief: Exam prep (exams, Exam Packs, practice)

**Your worktree:** `novi-worktrees/exam-prep` · **Branch:** `feature/exam-prep` ·
**Preview:** http://localhost:5177 (`make dev` here; the main app must be running)

## The goal
Novi prepares the student for every exam without being asked:
- Exam Packs are built automatically at T-14/7/3: a study guide plus verified practice exams, all
  citing the student's own notes.
- Practising should feel like a real exam, followed by honest feedback.

Exam prep is where the student sees upcoming exams and deadlines, opens packs, takes timed practice
exams and tracks progress.

## Where it stands (read the code to confirm)
- The Exam agent (`app/tools/exam.py`, `prompts/exam_agent.md`, verifier `prompts/exam_verifier.md`)
  runs in `handle_build_exam_pack`, including focused on-demand exams from Ask Novi (focus + duration).
- Pages: `pages/Exams.tsx` (list) and `pages/ExamPack.tsx` (study guide, timed practice, reveal,
  self-score, print). Both still have the v1 layout, restyled only by the colour remap.
- Assignments come from the calendar sync (Schedule) and have a `done` flag.
- The readiness ring from the reference design is a **stub** behind `readiness_score`
  (`config/features.json`, off).

## What "finished" means
1. **Exams overview** in the reference style:
   - upcoming exams with countdown, pack status (next build date or current version) and "build now";
   - add, edit and delete an exam (date, title, scope note);
   - past exams uploaded per course.
2. **Deadlines:** assignments from the calendar, grouped by week, with mark done / undo and links to the
   course.
3. **Pack page:** version history ("v2 added this week's notes"), study guide with source links, and
   practice exams with a proper exam mode (timer, question navigation, autosave, submit).
4. **Feedback and readiness:**
   - after self-scoring against the rubric, show per-topic results across attempts;
   - replace the readiness stub with a **real** metric computed from attempts. Document the formula,
     then ask the integrator to turn the `readiness_score` flag on. Never show invented numbers.
5. **Scope:** show what goes into the exam (topics and weeks) and let the student adjust it.
   Novi-initiated scope changes must go through an approval card (UX.md §7).
6. **Known bugs in your area** (`docs/SYSTEM_WALKTHROUGH.md` Appendix C; line numbers are from v1):
   - **C-4:** exam days-left uses the UTC date (the `app/tools/exam.py` side).
   - **C-9:** printing with solutions can run before the solutions are loaded.
7. Tests in `tests/test_view_exam_prep.py`, using the scripted provider for pack builds (see
   `tests/test_exam_pack.py`).

## Boundaries
- You own `app/api/routers/exams.py`, `app/tools/exam.py`, the exam prompts (bump `version:` when you
  change them), exam/assignment routes in `setup.py`, `handle_build_exam_pack`, `pages/Exams.tsx` and
  `pages/ExamPack.tsx`.
- Creating an exam must go through `cards.create_exam_with_followups` (it triggers the past-exams card).
  Cards are created via `app/orchestrator/cards.py` (Overview's).
- Past-exam uploads are processed by Courses' upload pipeline; link to it rather than re-implementing.
- Reserved migration id: `0007`, e.g. topic scores per attempt.
