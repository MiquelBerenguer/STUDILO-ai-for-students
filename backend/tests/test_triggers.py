"""Proactive triggers driven by the Planner with an injected clock."""

from __future__ import annotations

from datetime import UTC, datetime

from tests import fixture_factory as ff
from tests.conftest import onboard
from tests.helpers import drain, upload

# Slot: Thermodynamics, Thursday (weekday 3) 09:00–11:00 UTC. 2026-10-01 is a Thursday.
AFTER_CLASS = datetime(2026, 10, 1, 11, 5, tzinfo=UTC)


def tick(client, now: datetime) -> list[str]:  # type: ignore[no-untyped-def]
    r = client.post("/api/v1/simulate/tick", json={"now": now.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()["actions"]


def _sessions(client, state: str | None = None) -> list[dict]:  # type: ignore[no-untyped-def]
    return client.get("/api/v1/sessions" + (f"?state={state}" if state else "")).json()


def test_class_ended_prompts_for_notes_once(client) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    assert tick(client, datetime(2026, 10, 1, 10, 30, tzinfo=UTC)) == []  # class still running
    actions = tick(client, AFTER_CLASS)
    assert len(actions) == 1 and actions[0].startswith("class_ended Thermodynamics 2026-10-01")
    assert tick(client, AFTER_CLASS) == []  # idempotent
    drain(AFTER_CLASS)
    [session] = _sessions(client)
    assert session["state"] == "awaiting_upload"
    inbox = client.get("/api/v1/inbox").json()
    prompt = next(n for n in inbox if n["kind"] == "upload_prompt")
    assert "Thermodynamics" in prompt["title"] and prompt["link"] == f"/upload?session={session['id']}"
    jobs = client.get("/api/v1/jobs").json()
    check = next(j for j in jobs if j["type"] == "check_missed_upload")
    assert check["state"] == "queued" and check["payload"]["session_id"] == session["id"]


def test_missed_slot_is_flagged_in_course_memory_then_cleared_by_late_upload(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    tick(client, AFTER_CLASS)
    drain(AFTER_CLASS)
    later = datetime(2026, 10, 1, 23, 30, tzinfo=UTC)  # > 12 h after 11:00
    actions = tick(client, later)
    assert any(a.startswith("missed") for a in actions)
    drain(later)
    [session] = _sessions(client)
    assert session["state"] == "missed" and session["missed_reason"]
    mem = client.get(f"/api/v1/courses/{ids['thermo']['id']}/memory").json()
    assert mem["missed_count"] == 1
    assert any(n["kind"] == "reminder" for n in client.get("/api/v1/inbox").json())
    # The scheduled check job later finds nothing to do (no duplicate event).
    drain(datetime(2026, 10, 2, 0, 0, tzinfo=UTC))
    assert sum(1 for j in client.get("/api/v1/jobs").json() if j["type"] == "missed_upload") == 1
    # Late upload: missed -> uploaded -> processed
    d = upload(client, ids["thermo"]["id"], "late.pdf", ff.text_pdf(), session_id=session["id"])
    assert d["state"] == "done"
    assert _sessions(client)[0]["state"] == "processed"


def test_no_class_prompts_outside_the_semester(client) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    assert tick(client, datetime(2027, 3, 4, 12, 0, tzinfo=UTC)) == []


def test_exam_approaching_at_t14_t7_t3_once_each(client) -> None:  # type: ignore[no-untyped-def]
    onboard(client)  # exam on 2026-10-22 (Thursday)
    def exam_actions(now: datetime) -> list[str]:
        return [a for a in tick(client, now) if a.startswith("exam_approaching")]
    assert exam_actions(datetime(2026, 10, 7, 8, tzinfo=UTC)) == []           # T-15
    assert exam_actions(datetime(2026, 10, 8, 8, tzinfo=UTC)) == ["exam_approaching Thermo midterm T-14"]
    assert exam_actions(datetime(2026, 10, 9, 8, tzinfo=UTC)) == []
    assert exam_actions(datetime(2026, 10, 15, 8, tzinfo=UTC)) == ["exam_approaching Thermo midterm T-7"]
    assert exam_actions(datetime(2026, 10, 19, 8, tzinfo=UTC)) == ["exam_approaching Thermo midterm T-3"]
    assert exam_actions(datetime(2026, 10, 20, 8, tzinfo=UTC)) == []
    jobs = [j for j in client.get("/api/v1/jobs").json() if j["type"] == "build_exam_pack"]
    assert sorted(j["payload"]["threshold"] for j in jobs) == [3, 7, 14]


def test_exam_added_late_triggers_once_at_the_nearest_threshold(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    client.post("/api/v1/exams", json={"course_id": ids["fluids"]["id"], "title": "Fluids quiz",
                                       "exam_date": "2026-10-20"})
    actions = [a for a in tick(client, datetime(2026, 10, 15, 8, tzinfo=UTC)) if "Fluids" in a]
    assert actions == ["exam_approaching Fluids quiz T-7"]


def test_manual_ui_actions_emit_the_same_events(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    r = client.post("/api/v1/events", json={"type": "class_ended", "slot_id": ids["slot"]["id"],
                                            "session_date": "2026-10-01"})
    assert r.status_code == 202 and r.json()["type"] == "class_ended"
    assert r.json()["payload"]["source"] == "manual"
    drain(AFTER_CLASS)
    assert _sessions(client)[0]["state"] == "awaiting_upload"
    r = client.post("/api/v1/events", json={"type": "class_slot_passed_without_upload"})
    assert r.status_code == 202 and r.json()["type"] == "missed_upload"
    drain(AFTER_CLASS)
    assert _sessions(client)[0]["state"] == "missed"
    r = client.post(f"/api/v1/exams/{ids['exam']['id']}/build-pack")
    assert r.status_code == 202 and r.json()["type"] == "build_exam_pack"


def test_local_timezone_is_respected(client) -> None:  # type: ignore[no-untyped-def]
    onboard(client, tz="Europe/Madrid")  # class ends 11:00 Madrid = 09:00 UTC (CEST)
    assert tick(client, datetime(2026, 10, 1, 8, 55, tzinfo=UTC)) == []
    assert len(tick(client, datetime(2026, 10, 1, 9, 5, tzinfo=UTC))) == 1
