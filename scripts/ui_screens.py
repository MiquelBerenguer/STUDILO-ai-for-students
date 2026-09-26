"""Capture UI screenshots with Playwright (dev tool only; not a product dependency).

Usage (servers must be running: backend :8000, frontend :5173):
  uv run --no-project --with playwright python scripts/ui_screens.py before
  uv run --no-project --with playwright python scripts/ui_screens.py after --timetable path/to/timetable.png

`before` walks the legacy 4-step onboarding + Today screen.
`after` walks the new 3-step onboarding (timetable screenshot → confirm → Novi feed), measures the time to
first value, and captures the feed, a live agent run and the command bar.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = "http://localhost:5173"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"


def shot(page: Page, folder: str, name: str) -> None:
    path = OUT / folder / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(600)
    # The v2 shell has a fixed sidebar/sticky header, which full-page capture smears; use a tall viewport instead.
    page.screenshot(path=str(path), full_page=folder == "before")
    print("saved", path.relative_to(OUT.parent.parent))


def before(page: Page) -> None:
    email = f"before-{uuid.uuid4().hex[:6]}@example.com"
    page.goto(f"{BASE}/register")
    shot(page, "before", "00-register")
    page.fill("#name", "Alex")
    page.fill("#email", email)
    page.fill("#password", "correct-horse-1")
    page.click("button:has-text('Create account')")
    page.wait_for_url("**/onboarding")
    shot(page, "before", "01-onboarding-step1-subjects")
    api = page.request
    th = api.post(f"{BASE}/api/v1/courses", data={"name": "Thermodynamics"}).json()
    fl = api.post(f"{BASE}/api/v1/courses", data={"name": "Fluid Dynamics"}).json()
    page.reload()
    page.click("button:has-text('Next')")
    shot(page, "before", "02-onboarding-step2-schedule-empty")
    now = datetime.now()
    wd = now.weekday()
    start = (now - timedelta(hours=2)).strftime("%H:%M")
    end = (now - timedelta(minutes=20)).strftime("%H:%M")
    if end <= start:
        start, end = "08:00", "09:00"
    api.post(f"{BASE}/api/v1/courses/{fl['id']}/slots", data={"weekday": wd, "start_time": start, "end_time": end})
    api.post(f"{BASE}/api/v1/courses/{th['id']}/slots", data={"weekday": (wd + 1) % 7, "start_time": "09:00",
                                                              "end_time": "11:00"})
    page.reload()
    page.click("button:has-text('Next')")
    page.click("button:has-text('Next')")
    shot(page, "before", "03-onboarding-step3-semester")
    api.put(f"{BASE}/api/v1/me/profile", data={"semester_start": (now - timedelta(days=30)).date().isoformat(),
                                               "semester_end": (now + timedelta(days=90)).date().isoformat()})
    api.post(f"{BASE}/api/v1/exams", data={"course_id": th["id"], "title": "Thermo midterm",
                                           "exam_date": (now + timedelta(days=7)).date().isoformat()})
    page.reload()
    for _ in range(3):
        page.click("button:has-text('Next')")
    shot(page, "before", "04-onboarding-step4-exams")
    page.click("button:has-text('Finish setup')")
    page.wait_for_url(f"{BASE}/")
    api.post(f"{BASE}/api/v1/simulate/tick", data={})
    page.wait_for_timeout(3500)
    page.reload()
    shot(page, "before", "05-today-home")


def after(page: Page, timetable: Path) -> None:
    t0 = time.monotonic()
    page.goto(f"{BASE}/")
    shot(page, "after", "01-onboarding-step1-drop-timetable")
    page.set_input_files("input[data-testid=timetable-file]", str(timetable))
    page.wait_for_selector("[data-testid=schedule-preview]", timeout=60_000)
    shot(page, "after", "02-onboarding-step2-confirm-week")
    page.click("[data-testid=confirm-schedule]")
    page.wait_for_selector("[data-testid=novi-feed]", timeout=30_000)
    elapsed = time.monotonic() - t0
    page.wait_for_timeout(1500)
    shot(page, "after", "03-onboarding-step3-novi-feed")
    print(f"time to first value (landing → Novi feed): {elapsed:.1f}s")
    api = page.request
    api.post(f"{BASE}/api/v1/simulate/tick", data={"now": datetime.now(UTC).isoformat()})
    page.wait_for_timeout(4000)
    page.reload()
    page.wait_for_selector("[data-testid=novi-feed]")
    shot(page, "after", "04-home-novi-feed-with-cards")
    # approval model + visible work, all zero-cost: a command that needs approval, a deterministic upload
    course = api.get(f"{BASE}/api/v1/courses").json()[0]
    exam_day = (datetime.now() + timedelta(days=20)).date()
    api.post(f"{BASE}/api/v1/exams", data={"course_id": course["id"], "title": f"{course['name']} midterm",
                                           "exam_date": exam_day.isoformat()})
    api.post(f"{BASE}/api/v1/command", data={"text": f"move my {course['name']} midterm to "
                                                     f"{(exam_day + timedelta(days=7)).isoformat()}"})
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from tests.fixture_factory import text_pdf  # noqa: E402  (dev script: reuse the test fixture generator)
    api.post(f"{BASE}/api/v1/uploads", multipart={"course_id": course["id"], "kind": "past_exam",
                                                  "files": {"name": "past-exam-2025.pdf", "mimeType": "application/pdf",
                                                            "buffer": text_pdf()}})
    page.wait_for_timeout(4000)
    page.reload()
    page.wait_for_selector("[data-testid=novi-feed]")
    page.locator("[data-testid=live-run] button").first.click()
    page.wait_for_timeout(1200)
    shot(page, "after", "06-approval-card-and-expanded-agent-run")
    page.keyboard.press("Meta+k")
    page.wait_for_selector("[data-testid=command-palette]")
    page.fill("[data-testid=command-palette] [data-testid=command-input]", "what did we cover last week in Fluids?")
    shot(page, "after", "05-command-bar")
    if elapsed > 60:
        sys.exit(f"time to first value {elapsed:.1f}s exceeds 60s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["before", "after"])
    ap.add_argument("--timetable", type=Path)
    args = ap.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        height = 900 if args.phase == "before" else 1500
        page = browser.new_context(viewport={"width": 1440, "height": height}).new_page()
        before(page) if args.phase == "before" else after(page, args.timetable)
        browser.close()
