# Brief: Ask Novi (command bar)

**Your worktree:** `novi-worktrees/ask-novi` · **Branch:** `feature/ask-novi` ·
**Preview:** http://localhost:5174 (`make dev` here; the main app must be running)

## The goal
Ask Novi is how the student gives Novi instructions in natural language: the input in the home hero and
the ⌘K overlay. It should feel like texting a very capable classmate. Novi understands, routes the
request to the right agent or action, shows the work live, and lands the result as a card. Never a fake
chat reply (UX.md §1, §6).

## Where it stands (read the code to confirm)
- Deterministic parser first (`app/command/parse.py`), then a typed JEV fallback on the cheap model
  (`app/command/service.py`).
- Intents today: `generate_exam`, `ask_course` (Q&A agent), `change_exam_date` (approval card), `open`,
  `status` (connected calendar, answered from records).
- UI in `frontend/src/components/CommandBar.tsx`: request pill, live run, result card, clarification
  chips.
- Every command is stored as `Event(type="command")`.

## What "finished" means
1. **More intents, deterministic first**, each backed by a real action. Suggested (confirm with the
   user):
   - "what's due this week / tomorrow" (assignments + exams, no AI);
   - "add an exam for Fluids on 12 Dec" (creates the exam through `cards.create_exam_with_followups`);
   - "mark the lab report done";
   - "upload notes for Thermo" (opens a dropzone, then a real upload);
   - "summarise topic X" (Q&A agent over the topic);
   - "connect my Atenea calendar" (opens the connect flow).
2. **Recent requests:** a short, clickable history in the ⌘K panel (from the `command` events), so the
   student can re-run or re-open a result.
3. **Clarifications that never dead-end:** missing course/exam/date always offers choices. Unknown
   requests suggest the closest intents, based on the student's real data.
4. **Suggestions from data:** chips that match the student's situation right now (exam soon → "Make me a
   1h exam on …").
5. **Result quality:** answers render with math and citations. A failed AI call gives a clear retry, not
   provider errors.
6. **Keyboard-first:** ⌘K, ↑/↓ through history and chips, Enter, Esc.
7. Tests for every new intent: parser unit tests (EN/ES/CA) plus integration tests with the scripted
   provider (`tests/test_view_ask_novi.py`).

## Boundaries
- You own `app/command/*`, `app/tools/qa.py`, `prompts/qa_agent.md` (bump its `version:` if you change
  it), `handle_answer_question` and `components/CommandBar.tsx`.
- Intents that act on another view's data must call that view's **existing** functions or endpoints,
  never duplicate them. Example: creating an exam goes through `app/orchestrator/cards.py`. If what you
  need doesn't exist, describe it in your summary for that view.
- The command bar also appears in the Overview hero (`pages/Feed.tsx`, owned by Overview). Keep
  `CommandPanel`'s props stable, or tell the integrator if they change.
- Reserved migration id if you need one: `0009`.
