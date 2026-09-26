# Brief: Schedule (timetable, onboarding, calendars, triggers)

**Your worktree:** `novi-worktrees/schedule` · **Branch:** `feature/schedule` ·
**Preview:** http://localhost:5176 (`make dev` here; the main app must be running)

## The goal
Novi follows the student's week by itself. Schedule is where the week lives:
- the timetable, and the 3-step onboarding that captures it from a screenshot, PDF, `.ics` or text
  (UX.md §8);
- the connected Atenea/Moodle calendar;
- the triggers that make Novi proactive: class ended, missed class, exams at T-14/7/3, daily calendar
  sync.

## Where it stands (read the code to confirm)
- Onboarding extraction is deterministic first (grid parser, `.ics`, text), then the cheap vision model
  (`app/onboarding/*`). The confirm step creates courses and slots and merges `(G)/(P)` groups.
- The Schedule page (`pages/Schedule.tsx`) shows a read-only week grid with delete, a re-import flow and
  the Connected calendars panel.
- The calendar sync is in `app/integrations/calendar_feed.py`. It is real with Atenea: the student's
  feed connected, but every event so far was school-wide and unmatched.
- Triggers: `app/agents/planner.py` (scheduler tick every 30 s) and handlers `handle_class_ended`,
  `handle_missed_upload`, `handle_sync_calendar`.

## What "finished" means
1. **Edit the week, not just view it:** add a class manually, edit time, room and group, move a class to
   another day, delete with undo. The grid should look like a real weekly calendar (time axis, blocks
   sized by duration, today highlighted, the current class marked).
2. **Semester and preferences:** semester start/end (offer the school calendar dates when known),
   timezone, and "flag a class as missed after N hours", asked progressively rather than as a form.
3. **Class history:** per week, which sessions got notes, which were missed, which are waiting, with a
   link to upload late notes (the upload flow itself belongs to Courses).
4. **Calendar ↔ course linking:** unmatched events whose name looks like one of the student's subjects
   should get a one-tap "this is MF(G)?" fix. Store the alias so future syncs match. School-wide items
   stay ignored. Show upcoming deadlines from the calendar on the Schedule page.
5. **Onboarding polish:** retries, a better fallback when nothing is read, and a clear camera flow on
   phones.
6. **Known bugs in your area** (`docs/SYSTEM_WALKTHROUGH.md` Appendix C; line numbers are from v1):
   - **C-2:** a manual class-ended event plus the scheduler produce duplicate upload prompts. Make the
     class-ended path idempotent.
   - **C-4:** days-left uses the UTC date instead of the student's timezone (the planner side).
   - **C-13:** the scheduler looks back only one day, so a server that was off all weekend leaves gaps.
7. Tests in `tests/test_view_schedule.py`. Include parser fixtures for any new timetable format.

## Boundaries
- You own:
  - backend: `app/onboarding/*`, `app/api/routers/onboarding.py`, `app/integrations/calendar_feed.py`,
    the calendar routes in `integrations.py`, slot/profile routes in `setup.py`, `app/agents/planner.py`,
    `app/tools/planner.py`, and handlers `handle_class_ended`, `handle_check_missed`, `handle_missed_upload`,
    `handle_sync_calendar`;
  - frontend: `pages/Schedule.tsx`, `pages/Onboarding.tsx`, `components/Timetable.tsx`.
- Feed cards are created through `app/orchestrator/cards.py` (Overview's). Add new card kinds by calling
  `create_card`. If a new kind needs UI treatment in `ActionCard.tsx`, say so in your summary.
- Reserved migration id: `0005`, e.g. for course aliases or slot group/type.
