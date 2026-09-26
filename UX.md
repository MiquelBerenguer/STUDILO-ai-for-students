# Novi — UX (v2: agentic)

Novi is a second student who works for you. The student should feel that **Novi does the work and asks
for approval**, not that they are operating a tool. This document replaces the v1 dashboard UX. The v1
screens that survive are described in §9.

Visual language: the reference design in `design/reference/`, screenshots in `docs/screenshots/reference/`.
Its tokens are kept as-is (ink `#172038`, muted `#7d8498`, line `#e8e9f0`, canvas `#f5f6fa`, primary
`#6558e8` / dark `#4e42cf` / soft `#efedff`, success, warm), as are its radii (card 1.35 rem, control
0.8 rem), soft panel shadow, Inter typography with tight-tracked titles and 0.12 em uppercase eyebrows,
the rotated spark brand mark, the dark gradient hero with the orbit, objective rows, decision cards and
pill prompts. **What changes is the interaction model, not the look.**

## 1. Principles → what they mean on screen

| # | Principle | On screen | Backed by |
|---|-----------|-----------|-----------|
| 1 | Novi is the main surface | Home = the **Novi feed**: what I did, what I need from you, what I'll do next | `GET /feed` |
| 2 | Proactive, not reactive | The feed opens with **action cards** Novi generated, each with a one-tap action | `cards` rows created by triggers and jobs (§4) |
| 3 | Visible work | **Live agent runs**: agent, current step in plain language, result; expandable trace | `agent_runs` / `agent_steps`, `GET /runs/live` |
| 4 | Autonomy with control | Low-risk actions happen and show **Undo**; high-risk actions arrive as **approval cards** | `agent_actions` (§7) |
| 5 | Natural language everywhere | **Command bar**: always visible in the hero, plus ⌘K anywhere | `POST /command` (§6) |

**Guardrails against fake agentic UX.**
- Every card, run, count or "next" item on screen comes from a DB row or a computation over real data.
- There is no "thinking…" animation without a running `agent_run`, and no canned chat replies (the
  reference's `sendMessage` returned fixed strings; that pattern is banned).
- Anything without a backend is a **stub**, hidden behind a feature flag in `config/features.json` and
  listed in §10.
- Cards, not chat bubbles: Novi's output is a card with an action or a result card with sources. There
  is no conversation transcript.

## 2. Information architecture

```
Novi (home feed) ── the default route "/"
│   ├─ command bar (hero) + ⌘K overlay (global)
│   ├─ Needs you ........ open action cards
│   ├─ Working now ...... live agent runs (expandable)
│   ├─ Since you were away  finished runs since last visit
│   └─ Next up .......... what Novi will do and when
├─ Schedule ............. week grid + class sessions (secondary)
├─ Courses → course ..... notes, course memory, sources (secondary; was "Subject")
├─ Exam prep ............ exams, packs, timed practice (secondary)
├─ Activity ............. every agent run, trace, LLM cost (secondary; the reference's "Progress")
└─ Settings ............. providers, models, profile, account, simulate
```

The sidebar, profile block and topbar from the reference are kept. The sidebar's first item is
**Novi** (the reference had "Overview" and "Novi" as separate pages; they merge). The primary topbar
button becomes **"Ask Novi ⌘K"** (the reference had "Add course" / "New instruction").

## 3. Home: the Novi feed

```
┌ sidebar ┐┌ topbar: SATURDAY, 26 SEPTEMBER · "Good afternoon, Alex"      [bell n] [✦ Ask Novi ⌘K] ┐
│ ✦ Novi  ││┌ HERO (dark gradient + orbit) ───────────────────────────────────────────────────┐ │
│ Schedule│││ ● WATCHING 4 CLASSES · 2 NEED YOU · 1 RUNNING                                     │ │
│ Courses │││ "Fluids ended 20 min ago — I'm waiting for your notes."   ← status line, derived │ │
│ Exam prep││ [ Tell Novi what to do…  e.g. make me a 1h exam on entropy          ↵ ]            │ │
│ Activity│││ chips: suggested intents (real, based on data: "Exam on Thermo", "Last week in…") │ │
│ Settings││└──────────────────────────────────────────────────────────────────────────────────┘ │
│ profile │├ NEEDS YOU (cards)                     ┬ NEXT UP                                      │
└─────────┘│ [card] [card] [card]                  │ 14:00  I'll ask for your Thermo notes         │
           ├ WORKING NOW (live runs)               │ 23:00  I'll check Fluids notes arrived        │
           │ ✦ Notes agent · Reading your photo…   │ Oct 8  I'll build the Thermo pack (T-14)      │
           │   ✓ Text was clear — no AI needed     ├ YOUR WEEK (today's classes, timeline)         │
           │   ● Adding to topic: Entropy          ├ HOW I WORK (autonomy policy, real rules)      │
           ├ SINCE YOU WERE AWAY (finished runs)   │                                              │
           │ ✓ Filed classe1.pdf → Entropy · no AI · Undo                                        │
           └─────────────────────────────────────────────────────────────────────────────────────┘
```

- **Hero status line** is computed by `GET /feed` (`status` field) from counts of open cards, running
  runs, today's slots and the next class end. The greeting uses the user's name, or "there" for a guest.
- **Needs you**: open cards sorted by priority (approval > upload prompt > question > info). Each card is
  a reference "decision card": eyebrow label, title, one sentence of reason, then one to three
  actions. Inline inputs (date, textarea, dropzone) live inside the card, so no navigation is needed.
- **Working now**: `LiveRun` components for runs in `running` state (§5).
- **Since you were away**: runs finished since `users.last_seen_at` (updated by `POST /feed/seen` when
  the feed is left), shown as the reference's "objective rows" with ✓ and an expandable trace.
  Autonomous actions show their Undo here.
- **Next up**: planned work computed from real schedules: the next class end (Planner will prompt),
  queued jobs with `run_after` (e.g. `check_missed_upload`), and upcoming exam thresholds (T-14/7/3).
- **Your week**: the reference timeline, fed by `class_slots` + `class_sessions` for today.
- **How I work**: the fixed autonomy policy from §7, as text. It is not a toggle: the reference's
  "Autonomy mode" switch had no backend, so it is a flagged stub (§10).
- **Empty states**:
  - New user: the feed shows the setup cards (claim account, first exam question) and "Next up" shows the
    first class end.
  - Nothing pending: "All caught up. I'll ping you when your next class ends (Thu 11:00)."
- **Errors**: a failed load shows an inline retry panel. A failed job becomes a `job_failed` card with
  Retry.

## 4. Card types and their triggers

All cards are rows in `cards` (the v1 `notifications` table, extended with `status`, `actions`,
`priority`, `dedupe_key`, `action_id`). They are created **only** by triggers and jobs; the UI never
invents them.

| Card kind | Trigger (backend source) | Example copy | One-tap actions | Autonomy |
|-----------|--------------------------|--------------|-----------------|----------|
| `upload_prompt` | Planner `class_ended` (`handlers.handle_class_ended`) | "Your Fluid Dynamics class ended 20 min ago — drop your notes here." | **Drop notes** (inline dropzone / camera) · Not today | ask |
| `missed_class` | `class_slot_passed_without_upload` → Course Memory deterministic handler | "You missed Thursday's Thermo class. Want a catch-up from your notes and the syllabus?" | **Catch me up** (→ `catch_up` job) · Upload late notes · Dismiss | ask |
| `catch_up_ready` | `catch_up` job finished | "Catch-up for Thu 24 Sep: likely covered Entropy and the Clausius inequality." | Read (expands, with citations) · Dismiss | result |
| `notes_filed` | `process_upload` finished | "Filed IMG_0001.jpg into Entropy (handwriting — transcribed with AI) · updated Thermo memory." | Open notes · **Undo** | auto + undo |
| `exam_pack_ready` | `build_exam_pack` finished (T-14/7/3 or manual) | "Thermo exam in 7 days. I refreshed your Exam Pack with this week's notes." | **Open pack** · Undo (removes this version) | auto + undo |
| `exam_date_needed` | First `class_ended` for a course with no exam (progressive disclosure) | "When is the exam for Fluid Dynamics?" | **Date picker → Save** · No exam | ask |
| `past_exams_wanted` | An exam is created for a course with no past exams | "Got past Thermo exams? Drop them and practice exams will match their style." | Drop files (kind = past exam) · Skip | ask |
| `syllabus_wanted` | First notes filed for a course with an empty syllabus | "Paste the Fluids syllabus so I can track the class pace." | Textarea → **Save** · Skip | ask |
| `approval` | Command bar high-impact intent (`change_exam_date`) | "Move Thermo midterm from 22 Oct → 15 Oct? I'll re-plan the Exam Pack reminders." | **Approve** · Reject | approval |
| `answer` | `answer_question` job (QA agent) finished | "Last week in Fluids you covered Bernoulli and pipe losses…" + sources | Open sources · Dismiss | result |
| `job_failed` | Any job ends `failed` for a user-visible pipeline (upload, pack, catch-up, answer) | "I couldn't finish the Thermo pack: no notes yet." | **Retry** · Dismiss | — |
| `account_claim` | Guest user created (onboarding) | "Save your account so your notes are safe." | Email + password → **Save** | ask |

Deduplication: `dedupe_key` (e.g. `exam_date_needed:<course>`) is unique per user, so a trigger never
creates the same question twice. Dismissed cards stay dismissed.

## 5. Live agent-run component (`LiveRun`)

```
┌ ✦ Notes agent · running · 0:07 ─────────────────────────────── [▾ steps] ┐
│ ✓ Checking what kind of file this is — photo (JPEG)                        │
│ ✓ Reading your photo… handwriting detected — transcribing with AI ($0.002) │
│ ● Adding to topic: Entropy                                                 │
└────────────────────────────────────────────────────────────────────────────┘
```

- Source: `GET /runs/live` returns runs that are `running`, or finished in the last 10 minutes, with
  their steps.
- Each step carries a **plain-language `label`**, produced server-side by `app/agents/describe.py` from
  the tool name, its arguments and its result. Examples: `check_legibility` passed → "Text was clear — no
  AI needed"; `run_ocr` → "Reading your photo…"; `classify_topic` → "Adding to topic: Entropy";
  `update_topic_note` → "Writing “Second law” into Entropy"; `verify_question` → "Checking question 3 —
  passed".
- **Streaming, not spinners.** Steps appear as they are committed (each step commits,
  `app/agents/base.py`). The client polls every 1 s while a run is `running` and stops afterwards. The
  pulsing dot is on the current step only; a finished run collapses to its result line.
- Expanding a run shows the full trace (tool inputs/outputs and LLM calls with cost), the same data as
  Activity.
- Uploads show the same component inline in the card that started them.

## 6. Command bar

- Always visible in the hero. ⌘K / Ctrl-K opens it as an overlay from any screen. `Esc` closes it.
- Suggested chips come from data: courses with exams → "Make me an exam on <course>"; last week's
  sessions → "What did we cover last week in <course>?".
- `POST /command {text}` → **deterministic parsing first** (keywords, dates, durations, fuzzy
  course/exam matching). If that is not conclusive, a **JEV-style typed classification** runs on the
  cheap model (`intent: Literal[…]`, typed slots, Pydantic-validated, one retry). Unknown → a help card
  listing what Novi can do.

| Intent | Examples | Resolves to | Result |
|--------|----------|-------------|--------|
| `generate_exam` | "make me a 1h exam on entropy", "practice exam Thermo" | course (fuzzy), topic focus, duration | `exam_requested` event → `build_exam_pack` job with focus + duration → live run → `exam_pack_ready` card |
| `ask_course` | "what did we cover last week in Fluids?", "explain the Clausius inequality" | course (optional), date range (optional), question | `answer_question` job (QA agent: `search_notes`, `get_course_sessions`, `read_sections`, `answer`) → live run → `answer` card with sources |
| `change_exam_date` | "move my Thermo exam to the 15th" | exam (fuzzy), new date | **approval card** (high impact). Approve → date changed, exam triggers re-planned; Undo available |
| `open` (navigation) | "open thermo notes", "show exams" | route | navigates; no job |

- **Ambiguity:** when a slot can't be resolved (two matching courses, no date), the response carries
  `needs` plus choices, and the bar shows them as chips ("Which exam? Thermo midterm · Thermo final").
- **Feedback:** the submitted request appears as a pill above the result, the live run streams below it,
  and the final card lands in "Needs you" or as a result card. There is no chat transcript.

## 7. Approval / undo model

| Risk | Actions | Behaviour |
|------|---------|-----------|
| **Low** (autonomous) | file notes into topics, create topics, update course memory, flag missed sessions, refresh Exam Packs at T-14/7/3 | Novi does it, then records an `agent_actions` row with `status=applied` and a snapshot of what changed (`effects`). The card shows **Undo** for 7 days. |
| **High** (approval) | change an exam date or scope, delete content | Novi records `agent_actions` with `status=proposed` and shows an `approval` card. **Approve** applies it (then Undo is available); **Reject** discards it. Nothing changes before approval. |

- **Undo** is a real inverse operation computed from `effects`:
  - Notes filing: removes the sections that upload created (and their vectors), restores sections it
    revised to their previous content, deletes topics it created if they end up empty, and restores
    the session summary, pace and open questions it touched. The upload is marked `undone`.
  - Pack refresh: deletes that pack version.
  - Exam date change: restores the previous date.
- Undo is refused (with a message) when later work depends on the result, e.g. a newer upload revised the
  same section.
- Everything is recorded, so the Activity screen shows approvals and undos next to agent runs.

## 8. Onboarding (workstream C)

**Targets:** under 60 s to first value, at most 3 steps, no deferrable step.

### Old flow (v1) vs new flow

| | Old (v1) | est. time | New (v2) | est. time |
|---|---|---|---|---|
| 1 | Register: name, email, password | ~30 s | **Drop your timetable**: screenshot, photo, PDF, `.ics` file or link, or pasted text, on one screen. A guest session is created silently. | ~10 s + extraction 2–10 s |
| 2 | Subjects form | ~45 s | **"Here's your week — looks right?"**: editable week preview. Low-confidence fields are highlighted. One tap to confirm. | ~10–20 s |
| 3 | Weekly schedule: one form row per class | ~2–3 min (8 classes × ~15 s) | **"You're set. I'll ping you when your next class ends"**: lands on the Novi feed with first cards | 0 s |
| 4 | Semester dates + timezone + delay | ~20 s | — deferred (timezone auto-detected; semester end optional, asked later) | — |
| 5 | Exam dates (optional) | ~40 s | — deferred to an `exam_date_needed` card after each subject's first class | — |
| | **Total** | **5 screens, ~4–5 min, account first** | **3 steps, ~25–45 s, account last** | |

### Principles in the implementation
- **Capture, don't configure.** `POST /onboarding/extract` accepts an image, PDF, `.ics` file, `.ics` URL or
  text. The extraction pipeline is deterministic first:
  - `.ics`: RRULE parsing.
  - PDF text layer or OCR boxes: a positional **grid parser** that finds the weekday header columns, the
    time rows and the cells.
  - Pasted text: a line regex (day + time range + subject [+ room / professor]).
  - Only when the deterministic confidence is low does it escalate to the **cheap vision / text model**
    with a typed schema (weekday `Literal`, `HH:MM`, end > start), validated with one retry.
  - Every decision is recorded in an agent trace (`onboarding` agent), so step 1 shows a live run too
    ("Reading your timetable… found 6 classes").
- **Confirm, don't enter.** The preview is an editable week grid. Each field shows a confidence dot;
  fields below 0.8 are highlighted amber ("check room"). Editing is inline, and "Looks right" is one tap.
- **Progressive disclosure.** Exam dates, past exams, syllabus and semester end are asked later as cards
  (§4), exactly when relevant. Nothing optional blocks the first session.
- **Account last.** Step 1 creates a **guest** user (no email). All data is scoped and cost-logged like any
  user. The `account_claim` card lets the student set email + password whenever they like. Guests
  can use everything; logging out as a guest warns that the data would be lost.
- Returning users use "I already have an account" (log in), linked from step 1.

### Errors and empty states
- Nothing found → "I couldn't read a timetable here", with the reason from the trace, and quick switches
  to another input ("Paste it as text instead").
- Partial extraction → the preview shows what was found plus an "Add a class" row.
- A vision model is unavailable → the deterministic result is kept (if any), with a warning.

## 9. Before / after, screen by screen (reference design → Novi v2)

| Reference screen / element | What it did | Novi v2 | Why |
|---|---|---|---|
| **Overview** (hero "Machine Learning starts in 28 min", Today's flow, Courses, Next exam, agent sidebar) | Dashboard: the student reads widgets and clicks "Mark class done" / "Upload notes" | **Merged into the Novi feed.** The hero keeps the gradient and orbit but states what Novi is doing and waiting for. "Today's flow" becomes *Your week* on the right. "Mark class done" is gone: the Planner detects class ends itself. | Principle 1 and 2 |
| Agent **sidebar** ("Daily briefing" bubbles, "Prepared for you", quick prompts, composer) | Chat panel beside a dashboard; fake replies | **Removed as a sidebar.** The briefing becomes *Since you were away* (real runs). "Prepared for you" becomes result cards. The composer becomes the command bar in the hero + ⌘K. | Principle 1 and 5; no fake chat |
| **Novi page** hero "I'm running your semester" + Autonomy toggle | Status banner, decorative toggle | Becomes the home hero with a **real status line** (counts). The toggle is replaced by the *How I work* policy card; the toggle itself is a flagged stub. | Guardrail: no control without behaviour |
| **Current objectives** (Working now 68%, Completed, Waiting) | Hardcoded rows and progress | *Working now* = **live agent runs** with plain-language steps (no fake %). *Completed* = *Since you were away*. *Waiting* = *Next up* (planned from schedules). | Principle 3 |
| **Decision card** (Plan changed · Keep / Undo) | Static, undo sent a chat message | **Approval cards** (Approve / Reject) and **Undo** on autonomous actions, backed by `agent_actions` | Principle 4 |
| "Novi learned" memory card | Invented insight | **Stub** behind `study_habits_insights` (no backend yet) | Guardrail |
| "Your guardrail: Ask before moving lectures" switch | Decorative | The rule is real and fixed (exam date changes always ask); shown as text | Guardrail |
| Readiness ring (72%) | Invented metric | **Stub** behind `readiness_score` (no backend yet) | Guardrail |
| Schedule / Courses / Exam prep / Progress nav | Separate pages | Kept as **secondary views**: Schedule (week grid), Courses (v1 Subject page: notes/memory/sources), Exam prep (v1 Exams + Pack), Activity (runs + costs = "Progress") | Drill-down |
| Topbar "Add course" | Manual entry | **Ask Novi ⌘K** | Principle 5 |

v1 app screens (`docs/screenshots/before/`):
- **Today** → Novi feed.
- The 4-step **onboarding wizard** → the 3-step capture flow.
- The **Upload** page → inline card dropzones. The full Upload page stays reachable from Courses for bulk
  uploads.
- **Subject**, **Exam Pack** (timed exams, print), **Activity** and **Settings** keep their v1 behaviour,
  restyled with the reference tokens.

## 10. Stubs and feature flags

Flags live in `config/features.json` (shared by the backend and frontend, served by `GET /meta`). A stub is
never rendered with invented data; when its flag is off it is not rendered at all.

| Flag | Default | UI element | Why it is a stub |
|------|---------|------------|------------------|
| `study_habits_insights` | off | "Novi learned" card (reference) | No agent learns study habits yet |
| `readiness_score` | off | Readiness ring on exams (reference) | No mastery model yet |
| `autonomy_toggle` | off | Autonomy mode switch (reference) | The policy is fixed in code (§7); a toggle without behaviour would be fake |

## 11. Notifications
- The bell shows the number of open cards and opens the feed. There is no separate inbox list.
- Browser notifications fire for new cards while a tab is open. On plain-HTTP LAN phones this does not
  work (secure-context rule); the feed itself is the reliable channel.
