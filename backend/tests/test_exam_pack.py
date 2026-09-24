from __future__ import annotations

from tests import fixture_factory as ff
from tests.conftest import onboard
from tests.helpers import drain, llm_calls, upload


def test_exam_pack_is_grounded_verified_and_complete(client, scripted) -> None:  # type: ignore[no-untyped-def]
    scripted.verify_fail_once = True  # first verification fails → agent must redraft that question
    ids = onboard(client)
    thermo = ids["thermo"]["id"]
    upload(client, thermo, "clase1.pdf", ff.text_pdf())
    upload(client, thermo, "foto.jpg", ff.handwriting_photo())
    upload(client, thermo, "examen_2025.pdf", ff.text_pdf(), kind="past_exam")

    job = client.post(f"/api/v1/exams/{ids['exam']['id']}/build-pack").json()
    drain()
    job = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["state"] == "succeeded", job["error"]
    pack_id = job["result"]["pack_id"]
    hidden = client.get(f"/api/v1/packs/{pack_id}").json()
    assert hidden["state"] == "ready" and hidden["trigger"] == "manual"
    assert all(q["solution_md"] is None for m in hidden["mock_exams"] for q in m["questions"])

    pack = client.get(f"/api/v1/packs/{pack_id}?reveal=true").json()
    assert len(pack["mock_exams"]) == 2
    note_sections = set()
    for t in client.get(f"/api/v1/courses/{thermo}/topics").json():
        note_sections |= {s["id"] for s in client.get(f"/api/v1/topics/{t['id']}/note").json()["sections"]}
    for mock in pack["mock_exams"]:
        assert len(mock["questions"]) == 2
        for q in mock["questions"]:
            assert q["state"] == "verified" and q["verification"]["passed"]
            assert q["solution_md"] and sum(r["points"] for r in q["rubric"]) == q["points"]
            assert set(q["cited_section_ids"]) <= note_sections and q["cited_section_ids"]
    assert pack["study_guide"] and all(set(g["cited_section_ids"]) <= note_sections for g in pack["study_guide"])
    assert set(pack["citations"]) <= note_sections
    # the rejected question was replaced, and verification used the verification model
    assert len(llm_calls(client, "exam_verification")) >= 5
    runs = client.get("/api/v1/activity/runs?agent=exam").json()
    steps = client.get(f"/api/v1/activity/runs/{runs[0]['id']}").json()["steps"]
    names = [s["name"] for s in steps if s["kind"] == "tool"]
    assert names.count("draft_question") == 5 and names[-1] == "save_exam_pack"
    assert any(n["kind"] == "exam_pack" for n in client.get("/api/v1/inbox").json())


def test_timed_attempt_locks_answers_after_submit(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    upload(client, ids["thermo"]["id"], "clase1.pdf", ff.text_pdf())
    job = client.post(f"/api/v1/courses/{ids['thermo']['id']}/practice-exam").json()
    drain()
    pack_id = client.get(f"/api/v1/jobs/{job['id']}").json()["result"]["pack_id"]
    mock = client.get(f"/api/v1/packs/{pack_id}").json()["mock_exams"][0]
    attempt = client.post(f"/api/v1/mock-exams/{mock['id']}/attempts").json()
    qid = mock["questions"][0]["id"]
    r = client.put(f"/api/v1/attempts/{attempt['id']}", json={"answers": {qid: "300 J"}, "submit": True})
    assert r.json()["submitted_at"]
    assert client.put(f"/api/v1/attempts/{attempt['id']}", json={"answers": {qid: "changed"}}).status_code == 409
    r = client.put(f"/api/v1/attempts/{attempt['id']}", json={"self_scores": {qid: 8}, "submit": True})
    assert r.json()["self_scores"] == {qid: 8.0}
