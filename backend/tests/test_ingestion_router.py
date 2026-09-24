"""Router fixture tests: one per branch, through the real upload API and orchestrator.

The OCR engine, legibility check, embeddings (hashing) and state machines are real. Only the LLM is the
scripted test provider, and we count how often the router escalated to it.
"""

from __future__ import annotations

from pathlib import Path

from tests import fixture_factory as ff
from tests.conftest import onboard
from tests.helpers import llm_calls, upload

REAL_PDF = Path(__file__).parent / "fixtures" / "real_text_notes.pdf"


def _paths(detail: dict) -> list[str]:
    return [f"{row['step']}:{row['path_taken']}" for row in detail["log"]]


def test_text_pdf_uses_text_layer_with_zero_llm_calls(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "notes.pdf", ff.text_pdf())
    assert d["state"] == "done", d
    assert d["detected_type"] == "pdf"
    assert "legibility:accept_text_layer" in _paths(d)
    assert not any(p.startswith(("ocr:", "vision:")) for p in _paths(d))
    assert llm_calls(client, "vision_transcribe") == [] and llm_calls(client, "jev_classification") == []
    assert "Primera llei" in d["extracted_md"]


def test_real_world_text_pdf_fixture(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "contexto.pdf", REAL_PDF.read_bytes())
    assert d["state"] == "done"
    assert _paths(d).count("legibility:accept_text_layer") == 3
    assert llm_calls(client, "vision_transcribe") == []


def test_garbled_pdf_falls_back_to_local_ocr_without_llm(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "garbled.pdf", ff.garbled_pdf())
    assert d["state"] == "done", d
    leg = next(r for r in d["log"] if r["step"] == "legibility")
    assert leg["path_taken"] == "ocr" and "dictionary" in leg["reason"]
    assert "ocr:local_ocr:accept_ocr" in _paths(d)
    assert llm_calls(client, "vision_transcribe") == []
    assert "energy is conserved" in d["extracted_md"]


def test_scanned_pdf_runs_ocr_and_accepts_clean_print(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "scan.pdf", ff.scanned_pdf())
    assert d["state"] == "done", d
    leg = next(r for r in d["log"] if r["step"] == "legibility")
    assert "no text layer" in leg["reason"] and leg["scores"]["has_text_layer"] is False
    ocr = next(r for r in d["log"] if r["step"] == "ocr")
    assert ocr["ocr_confidence"] > 0.85 and ocr["path_taken"] == "local_ocr:accept_ocr"
    assert llm_calls(client, "vision_transcribe") == []


def test_handwriting_photo_escalates_to_vision_model(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "IMG_2041.HEIC.jpg", ff.handwriting_photo())
    assert d["state"] == "done", d
    assert d["detected_type"] == "jpeg"
    ocr = next(r for r in d["log"] if r["step"] == "ocr")
    assert ocr["path_taken"] == "local_ocr:vision" and ocr["scores"]["kind"] == "handwriting"
    vision = next(r for r in d["log"] if r["step"] == "vision")
    assert vision["model_used"] == "scripted/vision-cheap" and vision["cost_usd"] > 0 and vision["tokens_in"] > 0
    assert len(llm_calls(client, "vision_transcribe")) == 1
    assert "$Q = \\Delta U + W$" in d["extracted_md"]


def test_equation_page_escalates_with_equation_reason(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "equations.png", ff.equation_page())
    ocr = next(r for r in d["log"] if r["step"] == "ocr")
    assert ocr["scores"]["kind"] == "equations" and "equation" in ocr["reason"].lower()
    assert "vision:vision_llm" in _paths(d)


def test_clean_photo_is_accepted_locally(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "board.png", ff.clean_photo())
    assert "ocr:local_ocr:accept_ocr" in _paths(d)
    assert llm_calls(client, "vision_transcribe") == []


def test_vision_outage_keeps_ocr_text_and_is_logged_not_silent(client, scripted) -> None:  # type: ignore[no-untyped-def]
    scripted.fail_models.add("vision-cheap")
    ids = onboard(client)
    d = upload(client, ids["thermo"]["id"], "photo.jpg", ff.handwriting_photo())
    assert d["state"] == "done"
    assert "vision:vision_unavailable:kept_ocr" in _paths(d)
    assert "with warnings" in d["status_message"]
    failed = [c for c in llm_calls(client, "vision_transcribe") if not c["ok"]]
    assert failed and "503" in failed[0]["error"]


def test_unsupported_file_rejected_before_processing(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    r = client.post("/api/v1/uploads", data={"course_id": ids["thermo"]["id"]},
                    files=[("files", ("notes.pdf", b"PK\x03\x04not-a-pdf", "application/pdf"))])
    assert r.status_code == 415


def test_subject_from_slot_and_topic_assignment(client) -> None:  # type: ignore[no-untyped-def]
    ids = onboard(client)
    course = ids["thermo"]["id"]
    first = upload(client, course, "a.pdf", ff.text_pdf())
    subj = next(r for r in first["log"] if r["step"] == "subject")
    assert "no AI needed" in subj["reason"]
    topic = next(r for r in first["log"] if r["step"] == "topic")
    assert topic["path_taken"] == "embedding:new"  # first notes → first topic, no LLM
    second = upload(client, course, "b.pdf", ff.text_pdf())
    topic2 = next(r for r in second["log"] if r["step"] == "topic")
    assert topic2["path_taken"] == "embedding:map" and second["topic_id"] == first["topic_id"]
    assert llm_calls(client, "jev_classification") == []
    other = upload(client, course, "c.txt", "Mecànica de fluids: equació de Bernoulli i viscositat del fluid "
                                            "en canonades, pèrdues de càrrega i nombre de Reynolds.".encode())
    topic3 = next(r for r in other["log"] if r["step"] == "topic")
    assert topic3["path_taken"].split(":")[0] in {"embedding", "jev", "jev_invalid_default_new"}
