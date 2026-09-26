"""Near-zero-friction onboarding: timetable extraction (3+ fixture timetables) and the 3-step journey."""

from __future__ import annotations

import time

import pytest

from app.api.routers.auth import guest_limiter
from tests import fixture_factory as ff
from tests.conftest import make_client
from tests.helpers import llm_calls

TRUTH = {(s, wd, st, en) for s, wd, st, en, _, _ in ff.TIMETABLE}


@pytest.fixture(autouse=True)
def _reset_limits() -> None:
    guest_limiter.reset()
    from app.api.routers.onboarding import extract_limiter
    extract_limiter.reset()


def _guest(app):  # type: ignore[no-untyped-def]
    c = make_client(app)
    r = c.post("/api/v1/auth/guest", json={"timezone": "Europe/Madrid"})
    assert r.status_code == 201, r.text
    assert r.json()["is_guest"] and r.json()["email"] is None
    return c


def _extract(c, *, file: tuple[str, bytes] | None = None, **form: str) -> dict:  # type: ignore[no-untyped-def]
    files = {"file": (file[0], file[1], "application/octet-stream")} if file else None
    r = c.post("/api/v1/onboarding/extract", data=form, files=files)
    assert r.status_code == 200, r.text
    return r.json()


def _key(slots: list[dict]) -> set[tuple[str, int, str, str]]:
    return {(s["subject"], s["weekday"], s["start"], s["end"]) for s in slots}


def _run_steps(c, run_id: str) -> list[dict]:  # type: ignore[no-untyped-def]
    return c.get(f"/api/v1/runs/{run_id}").json()["steps"]


def test_clean_screenshot_is_parsed_without_ai(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, file=("timetable.png", ff.timetable_screenshot()))
    assert ex["method"] == "grid" and ex["confidence"] >= 0.75
    assert _key(ex["slots"]) == TRUTH
    thermo = next(s for s in ex["slots"] if s["weekday"] == 0)
    assert thermo["room"] == "Aula A2-101" and thermo["professor"] == "Garcia"
    assert llm_calls(c) == []  # deterministic path: no model call, $0
    labels = [s["label"] for s in _run_steps(c, ex["run_id"])]
    assert any(label.startswith("Read the timetable grid: 5 classes") for label in labels)


def test_pdf_timetable_uses_the_text_layer(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, file=("horari.pdf", ff.timetable_pdf()))
    assert ex["method"] == "grid" and _key(ex["slots"]) == TRUTH
    assert all(s["confidence"]["subject"] == 1.0 for s in ex["slots"])  # text layer, not OCR
    assert llm_calls(c) == []
    steps = _run_steps(c, ex["run_id"])
    assert next(s for s in steps if s["name"] == "extract_text")


def test_phone_photo_at_an_angle_escalates_to_cheap_vision(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, file=("IMG_2041.jpg", ff.timetable_photo()))
    steps = _run_steps(c, ex["run_id"])
    names = [s["name"] for s in steps]
    assert names.index("grid_parse") < names.index("escalate_timetable")  # deterministic attempt first
    assert ex["method"] == "vision" and _key(ex["slots"]) == TRUTH
    [call] = llm_calls(c, "timetable_extraction")
    assert call["reason"].startswith("timetable: grid parser not confident")
    friday = next(s for s in ex["slots"] if s["weekday"] == 4)
    assert friday["confidence"]["time"] < 0.8  # "unsure" → highlighted in the confirm step


def test_ics_file_gives_slots_and_exam_dates(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, file=("calendar.ics", ff.timetable_ics()))
    assert ex["method"] == "ics" and _key(ex["slots"]) == TRUTH
    assert ex["exams"] == [{"subject": "Thermodynamics", "title": "Examen final Thermodynamics", "date": "2027-01-15"}]
    assert next(s for s in ex["slots"] if s["weekday"] == 4)["professor"] == "Vidal"


def test_pasted_text(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, text=ff.TIMETABLE_TEXT)
    assert ex["method"] == "text" and _key(ex["slots"]) == TRUTH
    assert {s["room"] for s in ex["slots"]} == {"Aula A2-101", "Aula TV1-102", "Aula 3", "Lab C4-005"}
    assert llm_calls(c) == []


def test_unreadable_text_falls_back_to_the_model_and_bad_links_are_refused(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, text="my timetable is the usual one from the campus site, thermo twice a week")
    assert ex["method"] == "llm_text"
    r = c.post("/api/v1/onboarding/extract", data={"url": "http://127.0.0.1:8000/cal.ics"})
    assert r.status_code == 422 and "private network" in r.json()["detail"]
    r = c.post("/api/v1/onboarding/extract", data={"url": "file:///etc/passwd"})
    assert r.status_code == 422


def test_confirm_creates_subjects_once_and_progressive_cards(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, file=("calendar.ics", ff.timetable_ics()))
    r = c.post("/api/v1/onboarding/confirm", json={"slots": ex["slots"], "exams": ex["exams"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["slots_created"] == 5 and out["exams_created"] == 1 and out["journey_state"] == "active"
    courses = c.get("/api/v1/courses").json()
    assert sorted(x["name"] for x in courses) == ["Calculus II", "Fluid Dynamics", "Physics Lab", "Thermodynamics"]
    assert next(x for x in courses if x["name"] == "Thermodynamics")["professor"] == "Garcia"
    kinds = {x["kind"] for x in c.get("/api/v1/feed").json()["cards"]}
    assert {"account_claim", "backfill_notes", "past_exams_wanted"} <= kinds
    # confirming again doesn't duplicate anything
    again = c.post("/api/v1/onboarding/confirm", json={"slots": ex["slots"]}).json()
    assert again["slots_created"] == 0 and len(c.get("/api/v1/courses").json()) == 4


def test_guest_claims_account_and_keeps_data(app) -> None:  # type: ignore[no-untyped-def]
    c = _guest(app)
    ex = _extract(c, text=ff.TIMETABLE_TEXT)
    c.post("/api/v1/onboarding/confirm", json={"slots": ex["slots"]})
    r = c.post("/api/v1/auth/claim", json={"email": "new@example.com", "password": "long-enough-1"})
    assert r.status_code == 200 and not r.json()["is_guest"]
    assert not [x for x in c.get("/api/v1/feed").json()["cards"] if x["kind"] == "account_claim"]
    other = make_client(app)
    assert other.post("/api/v1/auth/login", json={"email": "new@example.com", "password": "long-enough-1"}).status_code == 200
    assert len(other.get("/api/v1/courses").json()) == 4  # same user, same data
    assert c.post("/api/v1/auth/claim", json={"email": "x@example.com", "password": "long-enough-1"}).status_code == 409


def test_guest_sessions_are_rate_limited(app) -> None:  # type: ignore[no-untyped-def]
    c = make_client(app)
    codes = [c.post("/api/v1/auth/guest", json={}).status_code for _ in range(21)]
    assert codes[:20] == [201] * 20 and codes[20] == 429


def test_e2e_fresh_user_to_novi_feed_in_three_steps_under_60s(app) -> None:  # type: ignore[no-untyped-def]
    """Definition of done: landing → Novi feed in 3 steps and < 60 s, from a timetable screenshot."""
    t0 = time.monotonic()
    c = make_client(app)
    assert c.get("/api/v1/auth/me").status_code == 401  # landing: nobody is logged in, no registration wall
    # Step 1 — "Drop your timetable": the drop creates the guest session silently, then reads the image
    assert c.post("/api/v1/auth/guest", json={"timezone": "Europe/Madrid"}).status_code == 201
    ex = _extract(c, file=("Screenshot 2026-09-26.png", ff.timetable_screenshot()))
    assert len(ex["slots"]) == 5
    # Step 2 — "Here's your week — looks right?": one tap
    assert c.post("/api/v1/onboarding/confirm", json={"slots": ex["slots"]}).status_code == 200
    # Step 3 — "You're set": the Novi feed, with real proactive content already there
    feed = c.get("/api/v1/feed").json()
    elapsed = time.monotonic() - t0
    assert feed["is_guest"] and feed["counts"]["classes"] == 5
    assert {"account_claim", "backfill_notes"} <= {x["kind"] for x in feed["cards"]}
    assert feed["next"] and feed["next"][0]["kind"] == "class_end"  # "I'll ping you when your next class ends"
    assert "Next: I'll ask for your" in feed["status_line"]
    assert c.get("/api/v1/auth/me").json()["journey_state"] == "active"
    assert elapsed < 60, f"time to first value {elapsed:.1f}s"
