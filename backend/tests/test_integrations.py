"""Connected calendars (Moodle/Atenea export) and UPC course guides. No network: fetchers are monkeypatched."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth.crypto import decrypt
from app.db.engine import user_session
from app.db.models import Assignment, CalendarFeed
from app.onboarding.extract import ExtractionError
from tests import fixture_factory as ff
from tests.conftest import make_client, onboard, register
from tests.helpers import drain, llm_calls
from tests.test_triggers import tick

URL = "https://atenea.upc.edu/calendar/export_execute.php?userid=4242&authtoken=abc123secret&preset_what=all"


@pytest.fixture
def calendar(monkeypatch):  # type: ignore[no-untyped-def]
    """Serve the Moodle fixture calendar for any URL; tests can swap the payload or make it fail."""
    state = {"data": ff.moodle_calendar(datetime.now(UTC).date()), "fail": None, "calls": 0}

    async def fake_fetch(url: str) -> bytes:
        state["calls"] += 1
        if state["fail"]:
            raise ExtractionError(state["fail"])
        return state["data"]  # type: ignore[return-value]

    monkeypatch.setattr("app.onboarding.extract.fetch_ics", fake_fetch)
    return state


def _cards(client, kind: str) -> list[dict]:  # type: ignore[no-untyped-def]
    return [c for c in client.get("/api/v1/feed").json()["cards"] if c["kind"] == kind]


def _connect(client) -> dict:  # type: ignore[no-untyped-def]
    r = client.post("/api/v1/calendars", json={"url": URL, "label": "Atenea"})
    assert r.status_code == 201, r.text
    return r.json()


def test_connect_stores_url_encrypted_and_never_returns_it(client, calendar) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    out = _connect(client)
    assert out["upcoming"] == 4 and out["job"]["type"] == "sync_calendar"
    assert "abc123secret" not in str(out) and "abc123secret" not in client.get("/api/v1/calendars").text
    user_id = client.get("/api/v1/auth/me").json()["id"]
    with user_session(user_id) as db:
        feed = db.scalar(select(CalendarFeed))
        assert "abc123secret" not in feed.url_enc and decrypt(feed.url_enc) == URL and feed.host == "atenea.upc.edu"
    assert _connect(client)["feed"]["id"] == out["feed"]["id"]  # same link twice → same feed


def test_sync_files_deadlines_exams_and_cards_without_ai(client, calendar) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    _connect(client)
    drain()
    [feed] = client.get("/api/v1/calendars").json()
    assert feed["stats"]["new"] == 3 and feed["stats"]["unmatched"] == 1 and feed["stats"]["ignored"] == 2
    assert feed["stats"]["unmatched_examples"] == ["Essay is due"]
    assignments = client.get("/api/v1/assignments").json()
    assert {a["title"] for a in assignments} == {"Lab report 1 is due", "Quiz 2 closes"}
    exams = [e for e in client.get("/api/v1/exams").json() if e["title"] == "Thermodynamics final exam"]
    assert exams and exams[0]["course_id"] == ids["thermo"]["id"]
    deadline_titles = {c["title"].split(" — ")[0] for c in _cards(client, "deadline")}
    assert deadline_titles == {"Lab report 1 is due", "Quiz 2 closes"}
    assert llm_calls(client) == []
    runs = client.get("/api/v1/activity/runs").json()
    assert any(r["agent"] == "calendar" and r["state"] == "succeeded" for r in runs)


def test_resync_updates_instead_of_duplicating_and_mark_done(client, calendar) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    feed_id = _connect(client)["feed"]["id"]
    drain()
    calendar["data"] = ff.moodle_calendar(datetime.now(UTC).date(), due_offset=6)  # teacher moved the deadline
    user_id = client.get("/api/v1/auth/me").json()["id"]
    with user_session(user_id) as db:
        db.get(CalendarFeed, feed_id).last_synced_at = datetime.now(UTC) - timedelta(days=2)
    assert any(a.startswith("calendar_sync") for a in tick(client, datetime.now(UTC)))  # the daily trigger
    drain()
    with user_session(user_id) as db:
        labs = list(db.scalars(select(Assignment).where(Assignment.title == "Lab report 1 is due")))
        assert len(labs) == 1 and labs[0].due_date == datetime.now(UTC).date() + timedelta(days=6)
    assert client.get("/api/v1/calendars").json()[0]["stats"]["updated"] == 1
    lab_card = next(c for c in _cards(client, "deadline") if c["title"].startswith("Lab report"))
    r = client.post(f"/api/v1/cards/{lab_card['id']}/act", json={"action": "mark_done"})
    assert r.status_code == 200 and "done" in r.json()["message"]
    assert next(a for a in client.get("/api/v1/assignments").json() if a["title"].startswith("Lab"))["done"] is True


def test_failed_refresh_becomes_one_card_and_recovers(client, calendar) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    _connect(client)
    calendar["fail"] = "The calendar link answered HTTP 403."
    drain()
    [feed] = client.get("/api/v1/calendars").json()
    assert feed["last_error"] == "The calendar link answered HTTP 403."
    assert len([c for c in _cards(client, "job_failed") if c["data"].get("feed_id")]) == 1
    calendar["fail"] = None
    _connect(client)  # reconnecting queues a fresh sync
    drain()
    assert client.get("/api/v1/calendars").json()[0]["last_error"] == ""
    assert not [c for c in _cards(client, "job_failed") if c["data"].get("feed_id")]


def test_private_addresses_are_refused(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/v1/calendars", json={"url": "http://127.0.0.1:8000/cal.ics"})
    assert r.status_code == 422 and "private network" in r.json()["detail"]


def test_onboarding_offers_calendar_card_and_connects_from_it(app, calendar) -> None:  # type: ignore[no-untyped-def]
    c = make_client(app)
    c.post("/api/v1/auth/guest", json={"timezone": "Europe/Madrid"})
    ex = c.post("/api/v1/onboarding/extract", data={"text": ff.TIMETABLE_TEXT}).json()
    c.post("/api/v1/onboarding/confirm", json={"slots": ex["slots"]})
    [card] = _cards(c, "connect_calendar")
    act = next(a for a in card["actions"] if a["id"] == "connect_calendar")
    assert act["type"] == "input" and act["input_type"] == "url"
    r = c.post(f"/api/v1/cards/{card['id']}/act", json={"action": "connect_calendar", "value": URL})
    assert r.status_code == 200 and r.json()["job"]["type"] == "sync_calendar"
    drain()
    assert _cards(c, "deadline")


def test_calendars_are_user_isolated(app, calendar) -> None:  # type: ignore[no-untyped-def]
    a, b = make_client(app), make_client(app)
    register(a, "a@example.com")
    register(b, "b@example.com")
    onboard(a)
    feed_id = _connect(a)["feed"]["id"]
    assert b.get("/api/v1/calendars").json() == []
    assert b.delete(f"/api/v1/calendars/{feed_id}").status_code == 404
    assert len(a.get("/api/v1/calendars").json()) == 1


# ------------------------------------------------------------------ course guides
@pytest.fixture
def guides(monkeypatch):  # type: ignore[no-untyped-def]
    seen: list[str] = []

    async def fake_get(url: str) -> bytes | None:
        seen.append(url)
        return ff.upc_guide_pdf("300021") if url.endswith("/ca/300021") else None

    monkeypatch.setattr("app.integrations.upc_guides._http_get", fake_get)
    return seen


def test_course_guide_fills_the_syllabus(client, guides) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    r = client.post(f"/api/v1/courses/{ids['fluids']['id']}/guide", json={"code": "300021"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "TERMO - Thermodynamics"
    syllabus = client.get(f"/api/v1/courses/{ids['fluids']['id']}").json()["syllabus"]
    assert "1. First law of thermodynamics" in syllabus and "3. Thermodynamic cycles" in syllabus
    assert "Closed and open systems." in syllabus  # the unit description is kept
    for noise in ("Dedicació", "Descripció", "Teoria: 6h", "autònom", "Pàgina", "Lab sessions"):
        assert noise not in syllabus  # workload/page noise and the next section are excluded
    assert guides == ["https://www.upc.edu/content/grau/guiadocent/pdf/ca/300021"]
    assert client.post(f"/api/v1/courses/{ids['fluids']['id']}/guide", json={"code": "999999"}).status_code == 422
    assert client.post(f"/api/v1/courses/{ids['fluids']['id']}/guide", json={"code": "abcde"}).status_code == 422


def test_syllabus_card_can_fetch_the_guide(client, guides) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import Course
    from app.orchestrator import cards

    ids = onboard(client)
    user_id = client.get("/api/v1/auth/me").json()["id"]
    with user_session(user_id) as db:
        cards.ask_syllabus(db, db.get(Course, ids["fluids"]["id"]))
    [card] = _cards(client, "syllabus_wanted")
    r = client.post(f"/api/v1/cards/{card['id']}/act", json={"action": "fetch_guide", "value": "300021"})
    assert r.status_code == 200 and "syllabus" in r.json()["message"]
    assert "Second law" in client.get(f"/api/v1/courses/{ids['fluids']['id']}").json()["syllabus"]


def test_first_sync_is_visible_and_status_is_answered_from_records(client, calendar) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    assert "No calendar is connected" in client.post("/api/v1/command", json={"text": "is my calendar synced?"}).json()["message"]
    _connect(client)
    drain()
    [card] = _cards(client, "calendar_connected")
    assert "filed 3" in card["body"] and "Essay is due" in card["body"]
    feed = client.get("/api/v1/feed").json()
    assert any(n["kind"] == "calendar" for n in feed["next"])  # "I'll re-check your … calendar"
    res = client.post("/api/v1/command", json={"text": "are you connected to my atenea tasks?"}).json()
    assert res["intent"] == "status" and res["method"] == "rules" and res["outcome"] == "info"
    assert res["message"].startswith("Yes — Atenea is connected") and "2 open deadline(s)" in res["message"]
    assert llm_calls(client) == []  # no AI anywhere in this flow
    drain()
    assert len(_cards(client, "calendar_connected")) == 1  # only once


def test_group_suffixes_become_one_course(app) -> None:  # type: ignore[no-untyped-def]
    c = make_client(app)
    c.post("/api/v1/auth/guest", json={"timezone": "Europe/Madrid"})
    slots = [{"subject": "ELECTRI(G)", "weekday": 0, "start": "08:00", "end": "10:00", "room": "Aula 3"},
             {"subject": "ELECTRI(P)", "weekday": 2, "start": "10:00", "end": "12:00", "room": "Lab 1"},
             {"subject": "MF(G)", "weekday": 1, "start": "08:00", "end": "10:00", "room": ""}]
    out = c.post("/api/v1/onboarding/confirm", json={"slots": slots}).json()
    assert sorted(x["name"] for x in out["courses"]) == ["ELECTRI", "MF"] and out["slots_created"] == 3
    rooms = sorted(s["location"] for s in c.get("/api/v1/slots").json())
    assert rooms == ["(G)", "(G) Aula 3", "(P) Lab 1"]
