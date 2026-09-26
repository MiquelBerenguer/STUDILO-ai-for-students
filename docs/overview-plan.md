# Overview rebuild: plan

Status: **approved** (with the change and answers in §0b). Branch `feature/overview`, preview
http://localhost:5175.

The Overview (`/`) becomes the student's calm "central brain". In 5 seconds they know what today looks
like, what's next, what's pending and how they're doing. Novi (Ask Novi) is where the work gets done.
The Overview shows what to do, and every pending item hands off to Novi in one tap.

## 0. Decisions already taken (from the discovery round)

| Topic | Decision |
|---|---|
| Alert module | Doesn't exist yet. **Overview builds it** as a new shared module `backend/app/alerts.py` (pure rules over user data). Overview uses it now and Ask Novi adopts it. Any rule change happens there. |
| Ask Novi handoff | Route contract **`/ask?context=<type>:<id>`**. Overview implements its side only and does **not** edit `CommandBar.tsx`. The contract is documented for the Ask Novi agent (§6). |
| Old feed content | Keep the hero **command bar** (`CommandPanel`, not forked). Keep **"Working now"** as one compact strip, shown only while an agent runs and expandable to `LiveRun`. **Remove** "Since you were away" and "How I work" from Overview and **move them to Activity** (with the approvals/undo history). |
| Docs | The new Overview replaces UX.md §3 and relaxes D-26 (Ask Novi becomes a chat). I don't edit UX.md/DECISIONS.md. The proposed text goes in the final summary. |
| Metrics | Honest only (§4). No invented percentages. |
| Test deps | Approved: `vitest`, `@testing-library/react`, `jsdom` (+ `@testing-library/jest-dom`, see Q3) and `@playwright/test` as frontend devDependencies. |
| Time zone | All times in the **user's** timezone (`/auth/me.timezone`), never the browser's. |

## 0b. Approval: change and answers

**Change: keep one-tap actions.** Each Pending row keeps its primary action inline (reusing
`ActionCard`'s inline actions), and "Do it with Novi" becomes the secondary option:

| Alert | Inline primary action | Secondary |
|---|---|---|
| `missing_notes` | **Drop notes** (dropzone / camera → `POST /uploads` with the session) | Do it with Novi |
| `task_due` | **Mark done** (`PATCH /assignments/{id}`, or the `deadline` card's `mark_done`) | Do it with Novi |
| `approval` | **Approve / Reject** (the card's actions) | Do it with Novi |
| `job_failed` | **Retry** (the card's action) | Do it with Novi |
| `exam_prep` | — | **Do it with Novi** (seed "Make me a practice exam for …") |

Answers:
1. Flag `ask_novi_chat` in `config/features.json` (off). Off → open ⌘K prefilled with `seed_message` via
   `usePalette().open()`. On → navigate to `/ask?context=…`.
2. `account_claim` stays out of Pending (profile menu only).
3. `@testing-library/jest-dom` approved.
4. Hand-written validator in `overview/schema.ts`, no zod.
5. Progress: the 3 courses needing attention first, then "Show all courses" → `/courses`.
6. Demo users only in throwaway databases, never the shared one.
7. The 7-day missing-notes window is right.

Ownership: `app/alerts.py`, `app/overview/*` and `frontend/src/overview/` are new Overview-owned files
(Ask Novi only imports `alerts.py`). `make test` gains one line: `npm run test`.

## 1. Layout

Max width ~56 rem, centred, one column on phones. On ≥ lg, Today and Next up sit side by side. Reading
order is always 1 → 6.

```
┌ topbar (unchanged: date, greeting, bell = pending count, "Ask Novi ⌘K") ───────────────────┐
│ ┌ 1 STATUS HEADER (hero, dark gradient) ─────────────────────────────────────────────────┐ │
│ │ Good afternoon, Alex                                                                    │ │
│ │ You're on track this week.            ← one deterministic status sentence               │ │
│ │ [ ✦ Tell Novi what to do…                                              ⌘K  ➤ ]          │ │ ← CommandPanel
│ └─────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ ● Novi is reading your Thermo photo… (only while a run is live)            [▾ details] ┐ │ ← Working-now strip
│ ┌ 6 SETUP (only if incomplete) ─ "Add your exam dates so I can plan your prep" [Finish with Novi] ┐
│ ┌ 2 TODAY ───────────────────────────┐ ┌ 3 NEXT UP ─────────────────────────────────────┐ │
│ │ 09:00  Thermodynamics · A2-101  ✓  │ │ Next class  Fluid Dynamics · Tue 11:00 · tomorrow │ │
│ │ 11:00  Fluid Dynamics · TV1  ◀ now │ │ Thermo midterm · Thu 22 Oct · in 3 days          │ │
│ │ 23:59  Lab report 1 due            │ │ Notes from 6 of 8 classes · 1 practice exam done │ │
│ └────────────────────────────────────┘ └──────────────────────────────────────────────────┘ │
│ ┌ 4 PENDING ──────────────────────────────────────────────────────────────────────────────┐ │
│ │ Notes missing: yesterday's Informatics II class           [Do it with Novi]             │ │
│ │ Lab report 1 is due today                                  [Do it with Novi]             │ │
│ │ Approve: move Thermo midterm to 15 Oct                     [Do it with Novi]             │ │
│ │ +2 more                                                                                  │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ 5 PROGRESS ─────────────────────────────────────────────────────────────────────────────┐ │
│ │ ● Thermodynamics   On track                  Notes from 6 of 8 classes · 5 of 7 units     │ │
│ │ ● Fluid Dynamics   Needs a bit of attention   Notes from 2 of 5 classes                   │ │
│ │ ● Calculus II      Just getting started       No classes yet                              │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

"Max 5 sections on screen": 1 through 5, with 6 in place of nothing when setup is incomplete. The
Working-now strip is a status line, not a section. Lists have at most 3 rows (Pending, Progress rows
wrap under "+N more" / "Show all courses" only if a student has more than 3 courses, see Q5).

## 2. Backend

### 2.1 Endpoint
`GET /api/v1/overview` in a **new router** `app/api/routers/overview.py` (Overview view; registered at
the end of `app/main.py`). One call feeds the whole page.

```python
class Section(BaseModel, Generic[T]):   # one failing section never breaks the page
    ok: bool
    data: T | None = None
    error: str | None = None             # short, user-safe; full traceback goes to the log

class OverviewOut(BaseModel):
    generated_at: datetime               # UTC
    timezone: str                        # user's tz, echoed for the client formatter
    today: date                          # user's local date
    status: Section[StatusOut]
    setup: Section[SetupOut]
    day: Section[TodayOut]
    next_up: Section[NextUpOut]
    pending: Section[PendingOut]
    progress: Section[ProgressOut]
    working: list[RunOut]                # running agent runs (reuses feed.run_out)
```

Each section is built in its own `try`. On error it does `log.exception(...)` and returns
`Section(ok=False, error="Couldn't load this part.")`, so the error is recorded, not silent. Status depends on
pending/setup: if those fail, status falls back to the neutral greeting only.

### 2.2 Layers (pure logic separate from I/O)

| File | Role | Pure? |
|---|---|---|
| `app/alerts.py` (**shared**) | `AlertInputs` (frozen dataclasses: slots, sessions, courses, exams, assignments, open cards, submitted attempts, now, tz) → `compute_alerts(inp) -> list[Alert]`; `load_alert_inputs(db, user, now)` (thin loader) | rules pure, loader I/O |
| `app/overview/logic.py` | `compute_status`, `compute_setup`, `compute_today`, `compute_next_up`, `compute_progress`, `held_classes`, `syllabus_units` | pure |
| `app/overview/load.py` | builds the input snapshot with a handful of `select()`s on the user-scoped session | I/O |
| `app/api/routers/overview.py` | route + per-section error boundaries + Pydantic schemas | I/O |

`held_classes(slots, sessions, now, tz, semester)` is the one shared primitive for "classes held". It
lives in `app/alerts.py` so alerts and progress count classes the same way.

## 3. Sections

For every section: **loading** = a skeleton shaped like the final content (not a generic bar),
**error** = a small calm inline note "Couldn't load this part. [Try again]" (refetches `/overview`),
**empty** = as listed below.

### 3.1 Status header
- **Data:** user name, local hour, `pending`, `setup`, `progress`, exams today.
- **Greeting:** "Good morning/afternoon/evening, {name}" from the local hour (tz). Guests: "Hi there".
- **Status sentence**, first matching rule:
  1. setup has no courses or no schedule → "Let's finish setting up so I can follow your week."
  2. an exam today → "Good luck with your {exam} today." (+ " 1 other thing can wait." if pending > 0)
  3. pending with a due time in the next 7 days → "{N} thing(s) need your attention before {weekday of earliest due}."
  4. pending > 0 → "{N} thing(s) need your attention. Novi can help with each one."
  5. any course "Needs a bit of attention" → "Mostly on track. One course could use a bit of attention."
  6. otherwise → "You're on track this week."
- **Empty:** never empty (rule 6). **Loading:** the greeting from `/auth/me` renders immediately, with a
  one-line shimmer for the sentence. **Error:** the greeting only.

### 3.2 Today
- **Data:** today's (local) slots within the semester window, today's sessions (note state),
  assignments due today.
- **Rows:** `{time, kind: class|task, title, course color, room?, state}`. Class state:
  `done` | `now` | `next` | `later`, plus note state `notes_in` | `waiting_notes` (soft label, no red).
  Tasks: due time (`due_at` local) or "today".
- **Highlight:** exactly one row: the current class, else the next item. It gets `aria-current="true"`.
- **Empty:** "No classes today." + "Next class: {weekday} {HH:MM}, {course}" (from the next-up
  computation). If there's no schedule at all, "Add your timetable in the setup card above" (points to §3.6).

### 3.3 Next up
- **Next class:** the first slot occurrence whose start > now (scan 14 days, respect the semester).
- **Next exam or task:** whichever is sooner of the next exam (`exam_date ≥ today`) and the next open
  assignment (`done = false`, due ≥ now). Only the closest one is shown.
- **Relative time**, computed server-side in local days: "now", "in 40 min", "today at 16:00",
  "tomorrow", "in 3 days", "in 2 weeks".
- **Exam readiness line** (only when the item is an exam), built only from real counts:
  "Notes from {with_notes} of {held} classes" · "{k of n units} covered" *only if* the syllabus has
  numbered units (§4), otherwise "{t} topics with notes" · "{p} practice exam(s) done" or
  "Practice not started".
- **Empty:** "Nothing scheduled yet." If there are no exams, "No exam dates yet"; if setup is
  incomplete, it points to §3.6.

### 3.4 Pending (uses `app/alerts.py` only)
- **Rules** (in `alerts.py`, each with a stable `ref = "<type>:<id>"`):

  | type | Source | Fires when |
  |---|---|---|
  | `missing_notes` | `held_classes` × sessions | class ended in the last 7 days (local) and its session isn't `uploaded`/`processed`. Merges the matching open `upload_prompt`/`missed_class` card (same `session_id`) |
  | `task_due` | `Assignment` | not done and due within 3 days, or overdue by ≤ 7 days. Merges the open `deadline` card (same `assignment_id`) |
  | `exam_prep` | `Exam` + attempts | exam in ≤ 14 days and 0 submitted practice attempts for that course |
  | `approval` | open `approval` card | always (`pending:<card_id>`) |
  | `job_failed` | open `job_failed` card | always (`pending:<card_id>`) |

  Not pending (calm by design): info/result cards (`notes_filed`, `answer`, `catch_up_ready`,
  `exam_pack_ready`, `calendar_connected`) and optional asks (`syllabus_wanted`, `past_exams_wanted`,
  `connect_calendar`). `exam_date_needed` feeds the **setup** card instead (Q2 covers `account_claim`).
- **Order (urgency):** tier, then due time ascending.
  1. due ≤ 24 h: task due today/overdue, exam ≤ 1 day without practice
  2. `approval`, `job_failed`
  3. `task_due` within 3 days
  4. `missing_notes` (most recent first)
  5. `exam_prep` (≤ 14 days)
- **Row:** one short title, one short reason, one button **"Do it with Novi"** → `/ask?context=<ref>` (§6).
- **"+N more"** when total > 3 → `/ask?context=pending:all`.
- **Empty:** "Nothing pending. You're up to date." with a soft check icon.

### 3.5 Progress (one compact row per course)
- **Data:** per course, `held`, `with_notes`, `topics_with_notes`, `syllabus_units`, `units_covered`,
  the next exam, `practice_done`.
- **Row:** colour dot · course name · state pill · one line of facts (from §4). No bars, no percentages.
- **Empty:** no courses → it points to the setup card. A course with nothing held yet → "Just getting started".

### 3.6 Setup incomplete (conditional)
- `missing = [c for c in ("courses", "schedule", "exam_dates") if not present]`, where `exam_dates` =
  no exam at all. Courses without their own exam show "No exam date yet" in their progress line (not in setup).
- Shown only if `missing` is non-empty. It's one card with one action, **"Finish setup with Novi"** →
  `/ask?context=setup:<missing joined by ,>`, and copy tailored to the first missing piece.
- While shown, Today / Next up / Progress show pointer empty states ("Once your timetable is in, your
  day shows here") instead of empty widgets.

### 3.7 Working-now strip
- Shown only while `working` is non-empty: "● Novi is {headline of newest run}" + "and N more". The
  disclosure (`aria-expanded`) expands to `LiveRun`. Polling: 1 s while running, else 30 s, plus refetch on
  window focus.

## 4. Metric definitions (exact)

- **Classes held** (`held_classes`): each slot occurrence `(slot, date)` with
  `date ≥ max(local date of slot.created_at, semester_start or -∞)`, `date ≤ semester_end or +∞`, and
  local end time `< now`. Ad-hoc sessions (uploads without a slot) are not counted as held classes; their notes
  still count as topics.
- **Class has notes:** a `ClassSession` for `(slot_id, date)` in state `uploaded` or `processed`.
- **Notes coverage:** "Notes from {with_notes} of {held} classes". Hidden when `held == 0`.
- **Syllabus units:** top-level numbered lines of `course.syllabus` (`^\s*\d{1,2}[.)]\s+\S`, dedup by
  number). There are units when `n ≥ 2`, else there's no denominator.
- **Units covered:** a unit counts if at least one topic *with ≥ 1 note section* matches its title through
  the existing deterministic matcher `app.command.parse.best_match` (read-only reuse). Shown as
  "{k} of {n} units" only when units exist, otherwise "{t} topics with notes".
- **Practice done:** `ExamAttempt` rows with `submitted_at` set, for practice exams in packs of the
  course (for the next exam: packs of that exam or course-level packs). Self-scores are **not** shown
  and don't change the label (no judgment). Zero means "Practice not started".
- **Course state** (neutral labels, soft colours: success-soft / warm-soft / canvas):
  - `getting_started` "Just getting started": `held < 2` and no exam within 14 days.
  - `needs_attention` "Needs a bit of attention": (`held ≥ 2` and `with_notes / held < 0.75`) **or**
    (exam within 14 days and `practice_done == 0`) **or** (`missing_notes` alerts for this course ≥ 2).
  - `on_track` "On track": otherwise.
  - The 0.75 threshold is internal and never shown.

## 5. Frontend

- `pages/Feed.tsx` is rewritten as the Overview page composed of small section components in a new
  folder `frontend/src/overview/` (`StatusHeader`, `Today`, `NextUp`, `Pending`, `Progress`,
  `SetupCard`, `WorkingStrip`, `SectionShell`, `format.ts`, `schema.ts`). Folder ownership: Overview (see
  the summary for AGENTS.md).
- **Data:** `useOverview()` appended to `hooks.ts`, validated at runtime by `overview/schema.ts` (see Q4).
  A payload that fails validation shows a page-level error with retry. A section with `ok = false` shows
  only that section's error.
- **Time formatting:** `format.ts` uses `Intl.DateTimeFormat(…, { timeZone: me.timezone })`. The server
  also sends local `HH:MM` strings and relative labels, so the UI never does date math in the browser's zone.
- **Shell:** Layout's bell shows the Pending total from `/overview`. The topbar greeting also uses the
  user's tz. `/feed` stays in place: `CommandBar.tsx` (Ask Novi) still uses it.
- **Activity** gets "Since you were away" (recent runs with undo), "Approvals & undo" (`GET /actions`)
  and "How I work" (policy via `GET /activity/policy` in `activity.py`).
- **A11y:** a `<section aria-labelledby>` per section, lists as `<ol>/<ul>`, real `<button>`/`<a>`,
  visible focus rings, `aria-live="polite"` on the status sentence and working strip, contrast ≥ 4.5:1
  on all text (the warm label uses the darker `#8a4d1c` on warm-soft), reduced-motion respected.
- **Responsive:** single column below `lg`. Tap targets ≥ 44 px, and nothing overflows at 320 px.

## 6. Ask Novi handoff contract (for the Ask Novi agent)

- **Route:** `/ask?context=<ref>`, `ref ∈ missing_notes:<session_id> | task_due:<assignment_id> |
  exam_prep:<exam_id> | pending:<card_id> | pending:all | setup:<courses,schedule,exam_dates>`.
- **Resolver:** `GET /api/v1/alerts/context?ref=<ref>` (in the overview router, backed by `alerts.py`)
  returns `{ref, type, title, reason, course_id?, session_id?, exam_id?, assignment_id?, card_id?,
  seed_message, suggested_actions[]}`. `seed_message` is a plain first message in the student's voice
  (e.g. "Help me with the notes from yesterday's Informatics II class"). `pending:all` returns the full
  ordered list. Refs that are unknown or resolved give `404` / `{resolved: true}`.
- **Until Ask Novi ships `/ask`:** see Q1. The Overview side is complete and tested against the
  resolver either way.

## 7. Demo seed

`backend/scripts/seed_demo.py` (dev-only, idempotent, no AI calls, no uploads to providers) creates
three users with fixed emails and a printed password, and all data relative to "now" in Europe/Madrid:
- `ontrack@demo.novi`: 3 courses, weekly slots created 3 weeks ago, all held classes with processed
  notes and topics, syllabus with numbered units, exam in 20 days, 1 submitted practice attempt, no pending.
- `behind@demo.novi`: missing notes for 3 recent classes (one `missed`), an assignment due today, an
  exam in 5 days with no practice, an open approval card.
- `newbie@demo.novi`: active user with 1 course, no slots, no exams.

It writes **only to the database in `DATABASE_URL`**. For screenshots and E2E I run *this branch's*
backend on a spare port against a **throwaway** database with empty API keys. The shared database is
never touched unless you ask for it (Q6).

## 8. Tests

- **Backend** `tests/test_view_overview.py` + `tests/test_alerts.py`: pure-function tests with fixed
  clocks. Cases: no data; first day of the semester (held = 0); exam today; all up to date; weekend;
  class in progress; timezone edge (UTC vs Madrid around midnight); syllabus with and without numbered
  units; card/alert merge and dedupe; urgency order; >3 pending. Plus an API test for `/overview` (shape,
  user isolation, one section forced to fail → the others still `ok`) and for `/alerts/context`.
- **Frontend** (vitest + RTL + jsdom): every section's empty, loading and error state, the setup card
  pointers, the "+N more" link, the tz formatting.
- **E2E** (`@playwright/test`, system Chrome like `scripts/ui_screens.py`): throwaway backend + seed
  `behind@demo.novi` → Overview → click "Do it with Novi" on the missing-notes row → assert the URL
  `/ask?context=missing_notes:<id>` and that the resolver returns that session's context. How far the
  "chat opened" assertion goes depends on Q1.
- `make test` gains `npm run test` (vitest). The E2E stays a separate `make e2e` (needs Chrome and
  free ports).

## 9. Implementation steps (each one is a mergeable commit)

1. **Alerts module:** `app/alerts.py` (rules, `held_classes`, loader) + `tests/test_alerts.py`. No UI change.
2. **Overview logic + endpoint:** `app/overview/*`, `routers/overview.py`, `/alerts/context`, per-section
   error boundaries, backend tests. `/feed` is untouched.
3. **Frontend test tooling:** vitest/RTL/jsdom devDependencies, `npm run test`, Makefile line.
4. **New Overview UI:** `overview/*` components, `useOverview`, schema validation, tz formatting, the
   rewritten `Feed.tsx`, component tests, bell count from `/overview`.
5. **Activity:** move "Since you were away", "Approvals & undo", "How I work" there.
6. **Demo seed** + screenshots of the 3 users (throwaway backend).
7. **E2E** with Playwright + `make e2e`.
8. **Docs:** update this plan to what was built, plus the final report (UX.md/DECISIONS/AGENTS/CHANGELOG
   proposals in the summary).

## 10. Risks

- `frontend/node_modules` is a **symlink to the main checkout**. Installing the approved devDependencies
  from this worktree writes into the main checkout's `node_modules` (additive, but shared). The
  `package.json`/lock change reaches master only at merge.
- The preview on :5175 talks to the **main backend (master)**, which has no `/overview` until merge. So
  the visual check and screenshots use this branch's backend on a throwaway DB (§7).
- `alerts.py` is new shared code that the Ask Novi agent will import. Its public API
  (`compute_alerts`, `load_alert_inputs`, `Alert`, `resolve_context`) is kept small and stable.

## 11. Open questions

1. **`/ask` before Ask Novi ships the chat.** The route doesn't exist on master. Options:
   (a) the button always goes to `/ask?context=…` and Ask Novi owns the route (until then it hits
   NotFound on master); (b) *recommended*: Overview registers nothing. Behind a new flag
   `ask_novi_chat` in `config/features.json`, off → the button opens the existing ⌘K palette prefilled with
   `seed_message` via `usePalette().open()` (no `CommandBar.tsx` edit), on → it navigates to `/ask`. The E2E
   asserts both paths.
2. **Guest `account_claim`:** should it be a lowest-urgency Pending item ("Save your account so your
   notes are safe") or stay out of the Overview (profile menu only)? I suggest keeping it out.
3. **Extra dev dep:** `@testing-library/jest-dom` (matchers like `toBeInTheDocument`). OK, or plain
   assertions only?
4. **Runtime schema on the client:** `zod` would be a new *runtime* dependency (small, widely used). The
   alternative is a hand-written validator in `overview/schema.ts`. Which do you prefer?
5. **More than 3 courses in Progress:** show the 3 that need attention first plus "Show all courses" (a link to
   `/courses`, not a menu), or list every course (one compact row each)?
6. **Seeding the shared DB:** should the demo users also exist in the shared database for the :5173 app,
   or only in throwaway DBs for screenshots and E2E?
7. **Missing-notes window:** is 7 days right for Pending (older gaps only affect progress)?
