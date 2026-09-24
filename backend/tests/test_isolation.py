"""Issue #6: user B cannot reach user A's chunks, notes, uploads or exams — via any endpoint or tool."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app import vectors
from app.agents.base import ToolContext, ToolError
from app.db import models as m
from app.db.base import utcnow
from app.db.engine import ScopeViolation, scoped_session_for
from app.llm.client import get_llm
from app.llm.embeddings import embed_texts
from tests import fixture_factory as ff
from tests.conftest import make_client, onboard, register
from tests.helpers import drain, upload


@pytest.fixture()
def two_users(app):  # type: ignore[no-untyped-def]
    a = make_client(app)
    a_id = register(a, "a@example.com")["id"]
    ids = onboard(a)
    thermo = ids["thermo"]["id"]
    up = upload(a, thermo, "a-notes.pdf", ff.text_pdf())
    job = a.post(f"/api/v1/exams/{ids['exam']['id']}/build-pack").json()
    drain()
    pack_id = a.get(f"/api/v1/jobs/{job['id']}").json()["result"]["pack_id"]
    pack = a.get(f"/api/v1/packs/{pack_id}?reveal=true").json()
    topic_id = up["topic_id"]
    section_id = a.get(f"/api/v1/topics/{topic_id}/note").json()["sections"][0]["id"]
    b = make_client(app)
    b_id = register(b, "b@example.com")["id"]
    return {"a": a, "b": b, "a_id": a_id, "b_id": b_id, "ids": ids, "upload": up, "topic_id": topic_id,
            "section_id": section_id, "pack": pack, "job_id": job["id"]}


def test_every_id_endpoint_hides_foreign_rows(two_users) -> None:  # type: ignore[no-untyped-def]
    t, b = two_users, two_users["b"]
    ids, pack = t["ids"], t["pack"]
    mock = pack["mock_exams"][0]
    run_id = t["a"].get("/api/v1/activity/runs").json()[0]["id"]
    notif_id = t["a"].get("/api/v1/inbox").json()[0]["id"]
    attempt = t["a"].post(f"/api/v1/mock-exams/{mock['id']}/attempts").json()
    probes = [
        ("GET", f"/api/v1/courses/{ids['thermo']['id']}"), ("PUT", f"/api/v1/courses/{ids['thermo']['id']}"),
        ("DELETE", f"/api/v1/courses/{ids['thermo']['id']}"), ("GET", f"/api/v1/courses/{ids['thermo']['id']}/topics"),
        ("GET", f"/api/v1/courses/{ids['thermo']['id']}/memory"), ("DELETE", f"/api/v1/slots/{ids['slot']['id']}"),
        ("POST", f"/api/v1/courses/{ids['thermo']['id']}/slots"), ("PATCH", f"/api/v1/exams/{ids['exam']['id']}"),
        ("DELETE", f"/api/v1/exams/{ids['exam']['id']}"), ("GET", f"/api/v1/uploads/{t['upload']['id']}"),
        ("GET", f"/api/v1/uploads/{t['upload']['id']}/file"), ("POST", f"/api/v1/uploads/{t['upload']['id']}/retry"),
        ("GET", f"/api/v1/topics/{t['topic_id']}/note"), ("GET", f"/api/v1/packs/{pack['id']}"),
        ("GET", f"/api/v1/packs/{pack['id']}?reveal=true"), ("GET", f"/api/v1/mock-exams/{mock['id']}?reveal=true"),
        ("POST", f"/api/v1/mock-exams/{mock['id']}/attempts"), ("GET", f"/api/v1/mock-exams/{mock['id']}/attempts"),
        ("PUT", f"/api/v1/attempts/{attempt['id']}"), ("POST", f"/api/v1/exams/{ids['exam']['id']}/build-pack"),
        ("POST", f"/api/v1/courses/{ids['thermo']['id']}/practice-exam"), ("GET", f"/api/v1/jobs/{t['job_id']}"),
        ("POST", f"/api/v1/jobs/{t['job_id']}/retry"), ("GET", f"/api/v1/activity/runs/{run_id}"),
        ("POST", f"/api/v1/inbox/{notif_id}/read"),
    ]
    bodies = {"PUT": {"name": "hijack"}, "POST": {"weekday": 1, "start_time": "08:00", "end_time": "09:00"},
              "PATCH": {"title": "hijack"}}
    for method, url in probes:
        body = {"answers": {}} if "/attempts/" in url and method == "PUT" else bodies.get(method)
        r = b.request(method, url, json=body)
        assert r.status_code == 404, f"{method} {url} -> {r.status_code} {r.text[:200]}"
    # B's event/upload attempts that reference A's objects
    assert b.post("/api/v1/events", json={"type": "class_ended", "slot_id": ids["slot"]["id"]}).status_code == 404
    assert b.post("/api/v1/events", json={"type": "exam_approaching", "exam_id": ids["exam"]["id"]}).status_code == 404
    r = b.post("/api/v1/uploads", data={"course_id": ids["thermo"]["id"]},
               files=[("files", ("x.pdf", ff.text_pdf(), "application/pdf"))])
    assert r.status_code == 404
    assert b.post("/api/v1/exams", json={"course_id": ids["thermo"]["id"], "title": "x",
                                         "exam_date": "2026-12-01"}).status_code == 404
    # A's data is intact after B's attempts
    assert t["a"].get(f"/api/v1/courses/{ids['thermo']['id']}").json()["name"] == "Thermodynamics"


def test_list_and_search_endpoints_return_nothing_foreign(two_users) -> None:  # type: ignore[no-untyped-def]
    b = two_users["b"]
    for url in ["/api/v1/courses", "/api/v1/slots", "/api/v1/exams", "/api/v1/assignments", "/api/v1/uploads",
                "/api/v1/sessions", "/api/v1/packs", "/api/v1/jobs", "/api/v1/inbox", "/api/v1/activity/runs",
                "/api/v1/activity/llm-calls", "/api/v1/activity/feed"]:
        assert b.get(url).json() == [], url
    assert b.get("/api/v1/notes/search?q=first law of thermodynamics energy").json() == []
    assert b.get("/api/v1/activity/summary").json()["total_cost_usd"] == 0
    assert b.get(f"/api/v1/notes/search?q=energy&course_id={two_users['ids']['thermo']['id']}").status_code == 404


def test_vector_store_is_partitioned_by_user(two_users) -> None:  # type: ignore[no-untyped-def]
    vec = asyncio.run(embed_texts(["first law of thermodynamics energy conserved"]))[0][0]
    a_db, b_db = scoped_session_for(two_users["a_id"]), scoped_session_for(two_users["b_id"])
    try:
        assert vectors.knn(a_db, two_users["a_id"], vec, k=5)
        assert vectors.knn(b_db, two_users["b_id"], vec, k=5) == []
        with pytest.raises(PermissionError):
            vectors.knn(b_db, "", vec)
    finally:
        a_db.close()
        b_db.close()


def test_scoped_session_filters_and_blocks_foreign_writes(two_users) -> None:  # type: ignore[no-untyped-def]
    b_db = scoped_session_for(two_users["b_id"])
    try:
        for model in (m.Course, m.Topic, m.NoteSection, m.Chunk, m.Upload, m.ExamPack, m.ExamQuestion, m.AgentRun,
                      m.LLMCall, m.IngestionLog, m.Job, m.Notification):
            assert b_db.scalars(select(model)).all() == [], model.__name__
        assert b_db.get(m.NoteSection, two_users["section_id"]) is None
        assert b_db.get(m.Upload, two_users["upload"]["id"]) is None
    finally:
        b_db.close()
    a_db = scoped_session_for(two_users["a_id"])
    course = a_db.scalars(select(m.Course)).first()
    a_db.expunge(course)
    a_db.close()
    b_db = scoped_session_for(two_users["b_id"])
    try:
        course.name = "hijack"
        b_db.add(course)
        with pytest.raises(ScopeViolation):
            b_db.flush()
        b_db.rollback()
        b_db.add(m.Course(name="spoof", user_id=two_users["a_id"]))
        with pytest.raises(ScopeViolation):
            b_db.flush()
    finally:
        b_db.rollback()
        b_db.close()


def test_agent_tools_cannot_reach_foreign_rows(two_users) -> None:  # type: ignore[no-untyped-def]
    from app.tools.exam import exam_tools
    from app.tools.ingestion import INGESTION_TOOLS
    from app.tools.notes import notes_tools

    b_id = two_users["b_id"]
    db = scoped_session_for(b_id)
    ctx = ToolContext(user_id=b_id, db=db, llm=get_llm(), now=utcnow())
    ctx.state.update(course_id=two_users["ids"]["thermo"]["id"], pack_id=two_users["pack"]["id"], n_exams=2,
                     n_questions=2)
    notes = {t.name: t for t in notes_tools()}
    exam = {t.name: t for t in exam_tools()}
    attempts = [
        (notes["get_topic_note"], {"topic_id": two_users["topic_id"]}),
        (notes["link_source"], {"section_id": two_users["section_id"], "upload_id": two_users["upload"]["id"]}),
        (notes["update_topic_note"], {"topic_id": two_users["topic_id"], "operation": "append_section",
                                      "heading": "x", "content_md": "x", "source_upload_ids": [two_users["upload"]["id"]]}),
        (exam["read_sections"], {"section_ids": [two_users["section_id"]]}),
        (exam["get_exam_scope"], {}),
        (INGESTION_TOOLS["detect_type"], {"upload_id": two_users["upload"]["id"]}),
        (INGESTION_TOOLS["classify_topic"], {"upload_id": two_users["upload"]["id"]}),
        (notes["get_topic_note"], {"topic_id": two_users["topic_id"], "user_id": two_users["a_id"]}),
    ]
    try:
        for tool, args in attempts:
            with pytest.raises(ToolError):
                asyncio.run(tool.invoke(ctx, args))
        hits = asyncio.run(notes["search_notes"].invoke(ctx, {"query": "first law energy"}))
        assert hits == []
    finally:
        db.close()
