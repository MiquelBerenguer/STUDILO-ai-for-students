"""End-to-end journey (Definition of Done), API-only, with an injected clock and the scripted test model."""

from __future__ import annotations

from datetime import UTC, datetime

from tests import fixture_factory as ff
from tests.conftest import make_client, onboard, register
from tests.helpers import drain, llm_calls, upload


def test_full_student_journey(app) -> None:  # type: ignore[no-untyped-def]
    c = make_client(app)
    me = register(c, "student@uni.edu")
    assert me["journey_state"] == "onboarding"
    assert c.post("/api/v1/me/complete-onboarding").status_code == 409  # cannot skip setup

    # 1. Setup: 2 subjects, weekly schedule, semester, one exam
    ids = onboard(c)
    assert c.get("/api/v1/auth/me").json()["journey_state"] == "active"

    # 2. A class slot ends (simulated clock) → upload prompt in the inbox
    thursday_after = datetime(2026, 10, 1, 11, 5, tzinfo=UTC)
    c.post("/api/v1/simulate/tick", json={"now": thursday_after.isoformat()})
    drain(thursday_after)
    prompt = next(n for n in c.get("/api/v1/inbox").json() if n["kind"] == "upload_prompt")
    session_id = prompt["data"]["session_id"]

    # 3. Upload a typed PDF for that class (zero LLM calls in ingestion) and a handwriting photo
    typed = upload(c, ids["thermo"]["id"], "classe1.pdf", ff.text_pdf(), session_id=session_id)
    assert typed["state"] == "done"
    ingestion_llm = [x for x in llm_calls(c) if x["task"] in ("vision_transcribe", "jev_classification")]
    assert ingestion_llm == []
    photo = upload(c, ids["thermo"]["id"], "IMG_0001.jpg", ff.handwriting_photo(), session_id=session_id)
    assert photo["state"] == "done" and len(llm_calls(c, "vision_transcribe")) == 1

    # 4. Content is in the right subject/topic notes, with sources
    topics = c.get(f"/api/v1/courses/{ids['thermo']['id']}/topics").json()
    assert topics and c.get(f"/api/v1/courses/{ids['fluids']['id']}/topics").json() == []
    notes = c.get(f"/api/v1/topics/{typed['topic_id']}/note").json()
    sources = {s["filename"] for sec in notes["sections"] for s in sec["sources"]}
    assert "classe1.pdf" in sources

    # 5. Course memory: session summary, pace, open question, and a flagged missed session (Fluids, Friday)
    friday_night = datetime(2026, 10, 3, 2, 30, tzinfo=UTC)  # Fluids ended Fri 14:00; missed after 12 h
    c.post("/api/v1/simulate/tick", json={"now": datetime(2026, 10, 2, 14, 5, tzinfo=UTC).isoformat()})
    drain(friday_night)
    c.post("/api/v1/simulate/tick", json={"now": friday_night.isoformat()})
    drain(friday_night)
    thermo_mem = c.get(f"/api/v1/courses/{ids['thermo']['id']}/memory").json()
    assert thermo_mem["sessions"][0]["state"] == "processed" and thermo_mem["sessions"][0]["summary_md"]
    assert thermo_mem["syllabus_position"] and thermo_mem["open_questions"]
    fluids_mem = c.get(f"/api/v1/courses/{ids['fluids']['id']}/memory").json()
    assert fluids_mem["missed_count"] == 1

    # 6. Exam approaching (T-14 via scheduler) → Exam Pack with study guide + ≥2 practice exams citing notes
    t14 = datetime(2026, 10, 8, 8, 0, tzinfo=UTC)
    actions = c.post("/api/v1/simulate/tick", json={"now": t14.isoformat()}).json()["actions"]
    assert "exam_approaching Thermo midterm T-14" in actions
    drain(t14)
    packs = c.get(f"/api/v1/packs?exam_id={ids['exam']['id']}").json()
    assert packs[0]["state"] == "ready" and packs[0]["trigger"] == "T-14"
    pack = c.get(f"/api/v1/packs/{packs[0]['id']}?reveal=true").json()
    assert pack["study_guide"] and len(pack["practice_exams"]) >= 2
    assert all(q["solution_md"] and q["cited_section_ids"] for mck in pack["practice_exams"] for q in mck["questions"])
    assert all(v["topic_title"] for v in pack["citations"].values())

    # 7. Every agent run and LLM call is visible with its cost
    summary = c.get("/api/v1/activity/summary").json()
    assert summary["total_cost_usd"] > 0 and summary["llm_calls"] > 0 and summary["deterministic_steps"] > 0
    agents = {r["agent"] for r in c.get("/api/v1/activity/runs?limit=200").json()}
    assert {"planner", "ingestion", "notes", "course_memory", "exam"} <= agents

    # 8. A second user sees none of it
    other = make_client(app)
    register(other, "other@uni.edu")
    assert other.get("/api/v1/courses").json() == []
    assert other.get(f"/api/v1/packs/{pack['id']}").status_code == 404
    assert other.get("/api/v1/notes/search?q=thermodynamics energy").json() == []
