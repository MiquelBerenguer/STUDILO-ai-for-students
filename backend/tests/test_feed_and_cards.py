"""Novi feed: real proactive cards, live runs with plain-language steps, undo and approval, command bar."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select

from app.db.engine import user_session
from app.db.models import AgentAction, NoteSection, TriggerLog
from tests import fixture_factory as ff
from tests.conftest import make_client, onboard, register
from tests.helpers import drain, upload
from tests.test_triggers import AFTER_CLASS, _sessions, tick


def _cards(client, kind: str | None = None) -> list[dict]:  # type: ignore[no-untyped-def]
    cards = client.get("/api/v1/feed").json()["cards"]
    return [c for c in cards if kind is None or c["kind"] == kind]


def _exam_date(client, exam_id: str) -> str:  # type: ignore[no-untyped-def]
    return next(e for e in client.get("/api/v1/exams").json() if e["id"] == exam_id)["exam_date"]


def _act(client, card: dict, action: str, value: str | None = None, status: int = 200) -> dict:  # type: ignore[no-untyped-def]
    r = client.post(f"/api/v1/cards/{card['id']}/act", json={"action": action, "value": value})
    assert r.status_code == status, r.text
    return r.json()


def test_feed_shows_plan_week_and_status(client) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    feed = client.get("/api/v1/feed").json()
    assert feed["counts"]["classes"] == 2
    kinds = {n["kind"] for n in feed["next"]}
    assert "class_end" in kinds and "exam_pack" in kinds  # computed from real slots / exam dates
    assert feed["status_line"] and feed["policy"] and feed["suggestions"]
    assert client.post("/api/v1/feed/seen").status_code == 204


def test_class_end_creates_upload_card_and_progressive_exam_question(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    fri = datetime(2026, 10, 2, 14, 5, tzinfo=UTC)  # Fluids (no exam yet) ends Fri 14:00
    tick(client, fri)
    drain(fri)
    [prompt] = _cards(client, "upload_prompt")
    assert "Fluid Dynamics" in prompt["title"]
    drop = next(a for a in prompt["actions"] if a["id"] == "drop_notes")
    assert drop["type"] == "upload" and drop["params"]["course_id"] == ids["fluids"]["id"]
    [ask] = _cards(client, "exam_date_needed")
    assert "Fluid Dynamics" in ask["title"]
    # Thermo already has an exam → never asked
    tick(client, AFTER_CLASS)
    drain(AFTER_CLASS)
    assert len(_cards(client, "exam_date_needed")) == 1
    # one tap: set the date → exam created, question closed, next progressive question appears
    out = _act(client, ask, "set_exam_date", "2026-12-15")
    assert "15 Dec" in out["message"]
    exams = client.get("/api/v1/exams").json()
    assert any(e["course_id"] == ids["fluids"]["id"] and e["exam_date"] == "2026-12-15" for e in exams)
    assert not _cards(client, "exam_date_needed")
    assert any(c["course_id"] == ids["fluids"]["id"] for c in _cards(client, "past_exams_wanted"))
    # uploading for that session answers the upload card
    upload(client, ids["fluids"]["id"], "n.pdf", ff.text_pdf(), session_id=prompt["data"]["session_id"])
    assert not _cards(client, "upload_prompt")


def test_live_run_steps_are_plain_language(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    up = upload(client, ids["thermo"]["id"], "classe1.pdf", ff.text_pdf())
    runs = client.get(f"/api/v1/runs/live?job_id={up['job_id']}").json()
    ingestion = next(r for r in runs if r["agent"] == "ingestion")
    labels = [s["label"] for s in ingestion["steps"]]
    assert any("text was clear — no AI needed" in label for label in labels)
    assert any(label.startswith("Adding to topic:") for label in labels)
    notes = next(r for r in runs if r["agent"] == "notes")
    assert notes["agent_name"] == "Notes agent" and notes["state"] == "succeeded"
    assert any("in your notes" in s["label"] for s in notes["steps"])
    assert notes["undo_action_id"]  # autonomous → undoable


def test_undo_notes_filing_restores_everything(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    tick(client, AFTER_CLASS)
    drain(AFTER_CLASS)
    [session] = _sessions(client)
    before_topics = client.get(f"/api/v1/courses/{ids['thermo']['id']}/topics").json()
    up = upload(client, ids["thermo"]["id"], "classe1.pdf", ff.text_pdf(), session_id=session["id"])
    assert up["state"] == "done"
    [filed] = _cards(client, "notes_filed")
    assert filed["undoable"] and any(a["id"] == "undo" for a in filed["actions"])
    assert "no AI needed" in filed["body"]
    assert _sessions(client)[0]["state"] == "processed"
    out = _act(client, filed, "undo")
    assert "Undone" in out["message"]
    assert client.get(f"/api/v1/uploads/{up['id']}").json()["state"] == "undone"
    assert client.get(f"/api/v1/courses/{ids['thermo']['id']}/topics").json() == before_topics
    assert _sessions(client)[0]["state"] == "awaiting_upload"  # back to before the upload
    assert client.get("/api/v1/notes/search", params={"q": "first law energy"}).json() == []
    _act(client, filed, "undo", status=409)  # card closed: nothing left to act on


def test_undo_refused_when_later_work_depends_on_it(client, app) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    first = upload(client, ids["thermo"]["id"], "a.pdf", ff.text_pdf())
    second = upload(client, ids["thermo"]["id"], "b.pdf", ff.text_pdf())
    user_id = client.get("/api/v1/auth/me").json()["id"]
    with user_session(user_id) as db:  # a later upload revised the section the first one created
        act = db.scalar(select(AgentAction).where(AgentAction.upload_id == first["id"]))
        sec = db.get(NoteSection, act.effects["created_sections"][0])
        sec.version = 2
        card_id = db.scalar(select(AgentAction.id).where(AgentAction.upload_id == second["id"]))
    assert card_id
    card = next(c for c in _cards(client, "notes_filed") if c["data"]["upload_id"] == first["id"])
    r = client.post(f"/api/v1/cards/{card['id']}/act", json={"action": "undo"})
    assert r.status_code == 409 and "changed by a later upload" in r.json()["detail"]


def test_missed_class_catch_up_is_a_real_job(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    upload(client, ids["thermo"]["id"], "earlier.pdf", ff.text_pdf())  # some notes to ground the catch-up
    tick(client, AFTER_CLASS)
    drain(AFTER_CLASS)
    later = datetime(2026, 10, 1, 23, 30, tzinfo=UTC)
    tick(client, later)
    drain(later)
    [missed] = _cards(client, "missed_class")
    assert not _cards(client, "upload_prompt")  # superseded by the missed-class card
    out = _act(client, missed, "catch_up")
    assert out["job"]["type"] == "catch_up"
    drain(later)
    [ready] = _cards(client, "catch_up_ready")
    assert "First law" in ready["title"] and ready["data"]["cited_section_ids"]
    runs = client.get("/api/v1/activity/runs").json()
    assert any(r["agent"] == "catch_up" and r["state"] == "succeeded" for r in runs)


def test_failed_job_becomes_retry_card(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    r = client.post(f"/api/v1/exams/{ids['exam']['id']}/build-pack")  # no notes yet → the pack can't be built
    assert r.status_code == 202
    drain()
    [failed] = _cards(client, "job_failed")
    out = _act(client, failed, "retry")
    assert out["job"]["state"] == "queued"


def test_exam_pack_card_undo_removes_version(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    upload(client, ids["thermo"]["id"], "classe1.pdf", ff.text_pdf())
    client.post(f"/api/v1/exams/{ids['exam']['id']}/build-pack")
    drain(datetime(2026, 10, 15, 8, tzinfo=UTC))
    [ready] = _cards(client, "exam_pack_ready")
    assert "Thermo midterm in" in ready["title"]
    assert len(client.get(f"/api/v1/packs?exam_id={ids['exam']['id']}").json()) == 1
    _act(client, ready, "undo")
    assert client.get(f"/api/v1/packs?exam_id={ids['exam']['id']}").json() == []


# ------------------------------------------------------------------ command bar
def _cmd(client, text: str) -> dict:  # type: ignore[no-untyped-def]
    r = client.post("/api/v1/command", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_command_change_exam_date_needs_approval_then_undo(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    user_id = client.get("/api/v1/auth/me").json()["id"]
    with user_session(user_id) as db:
        db.add(TriggerLog(key=f"exam_approaching:{ids['exam']['id']}:T-14"))
    res = _cmd(client, "move my Thermo exam to 2026-11-05")
    assert res["intent"] == "change_exam_date" and res["method"] == "rules" and res["outcome"] == "proposal"
    exam_id = ids["exam"]["id"]
    assert _exam_date(client, exam_id) == "2026-10-22"  # nothing changes before approval
    [card] = _cards(client, "approval")
    out = _act(client, card, "approve")
    assert "5 Nov" in out["message"]
    assert _exam_date(client, exam_id) == "2026-11-05"
    with user_session(user_id) as db:  # T-14/7/3 re-planned for the new date
        assert db.scalar(select(TriggerLog).where(TriggerLog.key.like("exam_approaching:%"))) is None
        act = db.scalar(select(AgentAction).where(AgentAction.kind == "change_exam_date"))
        assert act.status == "applied" and act.effects["previous_date"] == "2026-10-22"
    r = client.post(f"/api/v1/actions/{act.id}/undo")
    assert r.status_code == 200, r.text
    assert _exam_date(client, exam_id) == "2026-10-22"


def test_command_reject_changes_nothing(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    _cmd(client, "postpone the thermo midterm to the 29th")
    [card] = _cards(client, "approval")
    _act(client, card, "reject")
    assert _exam_date(client, ids["exam"]["id"]) == "2026-10-22"


def test_command_generate_exam_with_focus_and_duration(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    upload(client, ids["thermo"]["id"], "classe1.pdf", ff.text_pdf())
    res = _cmd(client, "make me a 1h exam on the first law for thermo")
    assert res["intent"] == "generate_exam" and res["outcome"] == "job"
    assert res["parsed"]["duration_minutes"] == 60 and res["parsed"]["topic"] == "first law"
    drain()
    [ready] = _cards(client, "exam_pack_ready")
    assert "60-min Thermodynamics exam on first law" in ready["title"]
    pack = client.get(ready["link"].replace("/packs/", "/api/v1/packs/")).json()
    assert len(pack["practice_exams"]) == 1 and pack["practice_exams"][0]["duration_minutes"] == 60


def test_command_ask_course_uses_class_history(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    # "last week" is relative to the real clock (the command bar uses it), so use last week's Thursday
    today = datetime.now(UTC).date()
    thursday = today - timedelta(days=today.weekday() + 7) + timedelta(days=3)
    client.put("/api/v1/me/profile", json={"semester_start": (thursday - timedelta(days=30)).isoformat(),
                                           "semester_end": (today + timedelta(days=90)).isoformat()})
    tick(client, datetime.combine(thursday, time(11, 5), tzinfo=UTC))
    drain()
    [session] = _sessions(client)
    upload(client, ids["thermo"]["id"], "classe1.pdf", ff.text_pdf(), session_id=session["id"])
    res = _cmd(client, "what did we cover last week in Thermodynamics?")
    assert res["intent"] == "ask_course" and res["outcome"] == "job"
    drain()
    [answer] = _cards(client, "answer")
    assert answer["title"].startswith("what did we cover") and session["id"] in answer["data"]["cited_session_ids"]
    runs = client.get("/api/v1/activity/runs").json()
    assert any(r["agent"] == "qa" and r["state"] == "succeeded" for r in runs)


def test_command_llm_fallback_and_clarification(client) -> None:  # type: ignore[no-untyped-def]
    onboard(client)
    res = _cmd(client, "quiz me please")  # no rule matches → typed JEV classification (scripted model)
    assert res["method"] == "llm" and res["intent"] == "generate_exam"
    assert res["outcome"] in ("job", "needs")
    res = _cmd(client, "make me an exam")  # two courses, none named → ask which
    assert res["outcome"] == "needs" and res["needs"] == "course" and len(res["choices"]) == 2


def test_cards_and_actions_are_user_isolated(app) -> None:  # type: ignore[no-untyped-def]
    a, b = make_client(app), make_client(app)
    register(a, "a@example.com")
    register(b, "b@example.com")
    ids = onboard(a)
    _cmd(a, "move my Thermo exam to 2026-11-05")
    [card] = _cards(a, "approval")
    assert b.post(f"/api/v1/cards/{card['id']}/act", json={"action": "approve"}).status_code == 404
    assert b.get("/api/v1/feed").json()["cards"] == []
    assert _cmd(b, "move my Thermo exam to 2026-11-05")["outcome"] == "help"  # B has no exams
    act_id = card["action_id"]
    assert b.post(f"/api/v1/actions/{act_id}/undo").status_code == 404
    assert _exam_date(a, ids["exam"]["id"]) == "2026-10-22"
    assert date.fromisoformat("2026-10-22")
