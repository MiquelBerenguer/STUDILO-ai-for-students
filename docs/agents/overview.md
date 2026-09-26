# Brief: Overview (the Novi feed) + app shell

**Your worktree:** `novi-worktrees/overview` · **Branch:** `feature/overview` ·
**Preview:** http://localhost:5175 (`make dev` here; the main app must be running)

## The goal
The home screen is Novi talking to the student: what it did since the last visit, what it needs now
(one-tap action cards), and what it will do next (UX.md §3). Also yours:
- the app shell: sidebar, bottom nav on phones, topbar, bell, profile menu;
- the secondary "system" screens: Activity (runs, traces, costs), Settings (providers, models, account,
  simulate) and the Auth pages.

Everything uses the reference design's visual language (`design/reference/`, tokens in
`frontend/src/index.css`).

## Where it stands (read the code to confirm)
- `GET /feed` (`app/api/routers/feed.py`) returns cards, live runs, since-last-visit runs, next items,
  today's classes and the autonomy policy.
- Cards come from triggers and jobs only (`app/orchestrator/cards.py`). Undo and approval are in
  `app/orchestrator/actions.py`. Plain-language step labels are in `app/agents/describe.py`.
- Activity and Settings still have the v1 layout, restyled only by the colour remap.

## What "finished" means
1. **Feed quality.**
   - "Since you were away" shows meaningful work only: no planner ticks that did nothing, and similar
     runs grouped ("Refreshed 3 things").
   - Cards are grouped and ordered sensibly (today first, per course where useful), with bulk
     dismiss of info cards.
   - Empty and error states for every section.
2. **The day at a glance.** "Your day" works on weekends and shows tomorrow when today is over. "Next up"
   stays short and relevant.
3. **Mobile.** The feed, cards, inline inputs and bottom nav all work well at phone width.
4. **Notifications.** A clear opt-in for browser notifications, and the bell shows what needs you.
5. **Activity screen** rebuilt in the reference style:
   - agent runs with expandable plain-language steps (reuse `LiveRun`);
   - AI spend per day, task and model;
   - the approvals/undo history (`GET /actions`).
6. **Settings screen** rebuilt in the reference style:
   - providers with masked keys and connection tests;
   - the model editor;
   - account: save a guest account, change password, log out, delete the account with confirmation;
   - the simulate panel, clearly labelled as a dev tool.
7. **Auth pages** in the reference style. Login and register sit behind "I already have an account"
   (the landing page is onboarding).
8. **Known bugs in your area** (`docs/SYSTEM_WALKTHROUGH.md` Appendix C; line numbers there are from v1):
   - **C-3:** the simulate tick writes real trigger keys. Isolate simulated runs so they can't suppress
     real triggers.
   - **C-8:** `models.yaml` is editable by any user. Decide a simple rule, e.g. the first registered
     user is the admin, and propose it.
   - **C-15:** no login rate limiting. Reuse `app/auth/ratelimit.py`.
9. Tests in `tests/test_view_overview.py`.

## Boundaries
- You own `feed.py`, `cards.py`, `actions.py`, `describe.py`, `activity.py`, `settings.py`, `auth.py`,
  `pages/Feed.tsx`, `pages/Activity.tsx`, `pages/Settings.tsx`, `pages/Auth.tsx`,
  `components/ActionCard.tsx`, `components/LiveRun.tsx`, `components/Layout.tsx` and
  `components/icons.tsx`.
- **Other views create cards through `cards.py`.** Keep `create_card`, `action`, `resolve`,
  `resolve_matching` and the `ask_*` helpers backward compatible, since other branches call them.
- The hero command bar is `CommandPanel` from `components/CommandBar.tsx` (owned by Ask Novi). Use it;
  don't fork it.
- Reserved migration id if you need one: `0008`.
