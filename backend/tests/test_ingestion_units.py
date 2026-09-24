"""Unit tests for the pure parts of the router: magic bytes, legibility, decisions, chunker."""

from __future__ import annotations

from app.ingestion import decisions
from app.ingestion.chunker import split_text
from app.ingestion.detect import detect_type
from app.ingestion.legibility import check_legibility
from app.ingestion.ocr import OcrResult
from tests import fixture_factory as ff


def test_detect_by_magic_bytes_not_extension() -> None:
    assert detect_type(ff.text_pdf()) == "pdf"
    assert detect_type(ff.clean_photo()) == "png"
    assert detect_type(ff.handwriting_photo()) == "jpeg"
    assert detect_type(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00") == "heic"
    assert detect_type("Apunts de classe: àèé".encode()) == "text"
    assert detect_type(b"\x00\x01\x02binary") == "unsupported"
    assert detect_type(b"PK\x03\x04docx") == "unsupported"


def test_legibility_signals() -> None:
    good = check_legibility("La primera ley de la termodinámica establece que la energía se conserva. " * 6)
    assert good.passed and good.dict_ratio > 0.9
    soup = check_legibility("xqzv kjhw pqlm trbn wqzx vbnq " * 20)
    assert not soup.passed and "dictionary" in soup.reason
    moji = check_legibility("TermodinÃ¡mica es la ciencia que estudia la energÃ­a y el calor " * 5)
    assert not moji.passed and "encoding" in moji.reason
    garbage = check_legibility("The first law \ufffd\ufffd\ufffd states (cid:12)(cid:14) energy is " * 8)
    assert not garbage.passed and "garbage" in garbage.reason
    empty = check_legibility("  \n 12 ")
    assert not empty.has_text_layer and not empty.passed


def _ocr(**kw: float) -> OcrResult:
    base = dict(text="x", mean_confidence=0.95, low_conf_ratio=0.0, lines=10, math_density=0.0,
                equation_line_ratio=0.0, ink_ratio=0.02, ink_outside_text_ratio=0.05, deskew_angle=0.0)
    base.update(kw)
    return OcrResult(**base)  # type: ignore[arg-type]


def test_ocr_decision_branches() -> None:
    assert decisions.decide_ocr(_ocr()).action == "accept_ocr"
    assert decisions.decide_ocr(_ocr(mean_confidence=0.6)).kind == "handwriting"
    assert decisions.decide_ocr(_ocr(low_conf_ratio=0.4)).kind == "handwriting"
    assert decisions.decide_ocr(_ocr(equation_line_ratio=0.8)).kind == "equations"
    assert decisions.decide_ocr(_ocr(ink_ratio=0.1, ink_outside_text_ratio=0.8)).kind == "diagram"
    assert decisions.decide_ocr(_ocr(lines=0, ink_ratio=0.2)).action == "vision"


def test_route_and_topic_bands() -> None:
    assert decisions.initial_route("pdf") == "text_layer"
    assert decisions.initial_route("heic") == "ocr"
    assert decisions.initial_route("text") == "plain_text"
    assert decisions.topic_band(None).action == "new"
    assert decisions.topic_band(0.9).action == "map"
    assert decisions.topic_band(0.2).action == "new"
    assert decisions.topic_band(0.6).action == "ask_jev"


def test_chunker_keeps_display_math_intact_and_splits_long_paragraphs() -> None:
    eq = "$$\n\\oint \\delta Q = \\oint \\delta W\n$$"
    text = "\n\n".join(["Intro paragraph. " * 20, eq, "After the equation. " * 20] * 4)
    chunks = split_text(text, chunk_size=400, overlap=50)
    assert len(chunks) > 3
    assert all(c.count("$$") % 2 == 0 for c in chunks)
    long = "Sentence number one is here. " * 200
    assert all(len(c) <= 700 for c in split_text(long, chunk_size=500, overlap=0))
