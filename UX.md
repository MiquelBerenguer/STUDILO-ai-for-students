# Studilo v1 — UX

Design goal: Studilo feels like a classmate who does the organising. The student acts mainly at two
moments: **after class** (drop in notes) and **before exams** (open the pack). Everything else is
proactive: inbox items, browser notifications, and an activity feed that says what the agents did,
in plain language.

## Principles
1. **One obvious next action per screen.** The Today screen always answers "what should I do now?".
2. **Show the work, not the plumbing.** Router and agent steps are shown as plain sentences ("Text
   layer found — no AI needed", "Handwriting detected — transcribing"), with details one click away.
3. **Every generated claim links to its source.** Note sections list their source files, and exam
   questions list the note sections they cite.
4. **Cost is visible.** Each LLM call shows its cost. Deterministic steps are labelled "no AI".
5. **Mobile-friendly upload.** The Upload screen works on a phone on the same Wi-Fi (camera capture).

## Navigation
Left sidebar (collapsible to a bottom bar on mobile): **Today · Upload · Subjects (list) · Exams ·
Activity · Settings**. Top bar: inbox bell (unread count) and user menu (log out).
Auth screens and the onboarding wizard are full-screen and have no sidebar.

## Screens

### 1. Auth — Log in / Register
- Email + password (min 8 chars). Switch link between the two forms.
- Errors: "Wrong email or password"; "An account with this email already exists"; field
  validation inline.
- After register → Onboarding. After login → Today, or Onboarding if setup is not finished.

### 2. Onboarding wizard (4 steps, progress bar, Back/Next)
1. **Subjects**: add 1+ subjects (name, colour, optional syllabus textarea). Empty state: "Add the
   subjects you are taking this semester". Next is disabled until there is one subject.
2. **Weekly schedule**: a week grid (Mon–Sun). "Add class" row: subject, day, start–end time. Shows the
   list of slots per day. Validation: end after start. Next is disabled until there is one slot.
3. **Semester dates**: start and end date, timezone (auto-detected from the browser, editable), and
   "Remind me about missing notes after N hours" (default 12).
4. **Exam dates**: add exams (subject, title, date, optional scope note such as "Units 1–4"). Optional
   assignments (title, due date). Can be skipped.
- **Finish** → `complete-onboarding`. A server-side 409 lists what is missing and jumps to that step.

### 3. Today
- **Header**: greeting and date.
- **Pending uploads** card (primary): classes that ended and are waiting for notes, each with an
  **Upload notes** button (opens Upload pre-filled with the session). Missed ones show a red "missed"
  badge. Empty: "All caught up — no notes pending".
- **Today's classes**: time-ordered list with a state chip (upcoming / in progress / ended). Ended
  classes without notes link to Upload.
- **Upcoming exams**: countdown in days, pack status (none / building / ready vX), and a **Build pack
  now** button. Empty: "No exams yet — add one in Exams".
- **Agent activity feed**: last ~15 events and agent runs in plain language, with cost or "no AI".
- First-run empty state (just onboarded): a 3-step explainer: "After each class, upload notes →
  Studilo organises them → exam packs appear before exams".

### 4. Upload
- Subject selector (pre-filled from `?session=`), a "which class" selector (recent sessions of that
  subject, or "no specific class"), and a kind toggle: **Class notes** / **Past exam**.
- Drag-and-drop zone plus "Choose files" and **Take photo** (`capture="environment"` on mobile). Accepts
  PDF, JPG/PNG/HEIC and .txt/.md; several files at once.
- **On your phone** panel: the LAN URL and a QR code ("Open this on your phone — same Wi-Fi").
- **Live progress list**, one row per file, polling the upload status: a state stepper (Received →
  Reading → Topic → Notes → Memory → Done) plus the router's plain-language message, e.g. "Page 2: Text
  layer found — no AI needed", "Handwriting detected (OCR confidence 0.62) — transcribing with AI". An
  expandable "How was this read?" shows the ingestion log (path, scores, model, tokens, cost).
- Errors: unsupported type (415) shown inline before upload; file too large; processing failure shows
  the error and a **Retry** button. Warnings (for example, vision unavailable so local OCR was kept)
  appear in amber.

### 5. Subject
- Header: subject name/colour, pace ("1.5 topics/week — Unit 3 of 8"), **Practice exam** button.
- Three tabs:
  - **Notes**: left = topic tree (indented by parent; section counts). Right = the rendered note
    (Markdown + KaTeX). Each section shows its heading, content, and **source chips** (file name and
    date, click to open the file). Search box (semantic search in this subject). Empty: "No notes
    yet. Upload notes after your next class".
  - **Course memory**: timeline of sessions (date, state chip: processed / missed / awaiting, and the
    summary), pace card, topic dependencies ("Second law ← builds on First law"), open questions with a
    **Resolve** button, and missed sessions highlighted.
  - **Sources**: table of uploads (file, date, kind, how it was read, status) with links.

### 6. Exams & Exam Pack
- **Exams list**: each exam with countdown, pack versions (state, trigger T-14/T-7/T-3/manual, date),
  **Build / Refresh pack**, and add/edit/delete exam.
- **Exam Pack page**: tabs **Study guide** | **Practice exams**.
  - Study guide: sections per topic, rendered with KaTeX, each with "Sources: Topic › Section" links
    to the note.
  - Practice exams: cards (title, duration, number of questions, total points). **Start timed exam** →
    full-screen timer, questions, answer textareas, **Submit** (auto-submit at 0). After submission:
    solutions, rubric with self-scoring inputs, per-question citations, and the verification badge.
  - **Export PDF**: print stylesheet (one section per page, no navigation). Uses browser "Save as PDF".
- States: building (progress text from the job, spinner), failed (error and **Retry**), and empty
  ("No pack yet: it will be built automatically 14 days before the exam, or build it now").

### 7. Activity / Costs
- Summary cards: total cost, LLM calls, deterministic steps, agent runs, unpriced calls.
- Charts as simple bars: cost by task, calls by model, and ingestion paths (text layer / local OCR /
  vision).
- **Agent runs** table (agent, mode llm/deterministic, goal, state, steps, cost, time). Clicking a run
  opens its trace: each step (LLM turn / tool / decision) with input/output JSON, latency, and the
  run's LLM calls.
- **LLM calls** table: task, provider/model, tokens in/out, cost, latency, fallback flag, errors.

### 8. Settings
- **Providers**: one row per provider with a configured/not configured badge, masked key (`sk-...a3f9`),
  the env var name, "used by" tasks, and **Test connection** (no token cost: it lists models). Keys are
  never shown or editable in the UI. The hint says "Edit .env and restart".
- **Models per task**: a table of task → provider/model/fallbacks with an edit form. Saving writes
  `models.yaml`. The server rejects a provider whose key is missing, with the key name in the error.
- **Profile**: timezone, semester dates, missed-notes delay.
- **Simulate (developer tools)**: "End a class now" (pick slot), "Flag the oldest pending class as
  missed", "Exam approaching" (pick exam), and "Run scheduler at…" (datetime). These emit the same
  events as the automatic triggers.

## Notifications
- Inbox bell: newest first. Click → navigate to its link and mark read. "Mark all read".
- Browser notifications: after the user allows them (prompt in the inbox dropdown), new unread items
  trigger `Notification` while the tab is open (polling every 15 s).

## Global states
- Loading: skeleton blocks, never blank pages.
- Network/server error: a toast with the message and a retry option, keeping the page usable.
- 401 anywhere → redirect to Log in (return to the same page after login).
- 404 on a resource (for example, another user's id) → "Not found" panel with a link back to Today.
