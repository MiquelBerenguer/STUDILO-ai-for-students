"""Pure routing decisions of the ingestion router. No I/O, fully unit-testable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.ingestion.detect import IMAGE_TYPES, FileType
from app.ingestion.legibility import LegibilityReport
from app.ingestion.ocr import OcrResult


@dataclass(frozen=True)
class OcrThresholds:
    min_mean_confidence: float = 0.85
    max_low_conf_ratio: float = 0.15
    max_math_density: float = 0.10
    max_equation_line_ratio: float = 0.35
    min_lines: int = 2
    diagram_min_ink_ratio: float = 0.03
    diagram_min_outside_ratio: float = 0.55


Route = Literal["text_layer", "ocr", "plain_text", "unsupported"]


def initial_route(ftype: FileType) -> Route:
    if ftype == "pdf":
        return "text_layer"
    if ftype in IMAGE_TYPES:
        return "ocr"
    if ftype == "text":
        return "plain_text"
    return "unsupported"


@dataclass(frozen=True)
class PageDecision:
    action: Literal["accept_text_layer", "ocr"]
    reason: str


def decide_pdf_page(report: LegibilityReport) -> PageDecision:
    if report.passed:
        return PageDecision("accept_text_layer", "Text layer found — no AI needed")
    if not report.has_text_layer:
        return PageDecision("ocr", "Scanned page (no text layer) — running local OCR")
    return PageDecision("ocr", f"Text layer is garbled ({report.reason}) — running local OCR")


@dataclass(frozen=True)
class OcrDecision:
    action: Literal["accept_ocr", "vision"]
    reason: str
    kind: Literal["clean", "handwriting", "equations", "diagram", "empty"]


def decide_ocr(ocr: OcrResult, th: OcrThresholds = OcrThresholds()) -> OcrDecision:
    """High confidence + plain prose → accept. Otherwise escalate to the cheapest vision model."""
    if ocr.lines < th.min_lines and ocr.ink_ratio > 0.01:
        return OcrDecision("vision", f"OCR found almost no text ({ocr.lines} lines) — transcribing with AI", "handwriting")
    if ocr.lines == 0:
        return OcrDecision("vision", "No text detected — transcribing with AI", "empty")
    if ocr.equation_line_ratio > th.max_equation_line_ratio or ocr.math_density > th.max_math_density:
        return OcrDecision("vision", f"Dense equations detected ({ocr.equation_line_ratio:.0%} equation lines) — "
                                     "transcribing math with AI", "equations")
    if ocr.mean_confidence < th.min_mean_confidence or ocr.low_conf_ratio > th.max_low_conf_ratio:
        return OcrDecision("vision", f"Handwriting detected (OCR confidence {ocr.mean_confidence:.2f}) — "
                                     "transcribing with AI", "handwriting")
    if ocr.ink_ratio > th.diagram_min_ink_ratio and ocr.ink_outside_text_ratio > th.diagram_min_outside_ratio:
        return OcrDecision("vision", f"Diagrams detected ({ocr.ink_outside_text_ratio:.0%} of ink outside text) — "
                                     "transcribing with AI", "diagram")
    return OcrDecision("accept_ocr", f"Clear printed text (OCR confidence {ocr.mean_confidence:.2f}) — no AI needed",
                       "clean")


# Topic assignment bands (DECISIONS D-13)
TOPIC_MAP_THRESHOLD = 0.80
TOPIC_NEW_THRESHOLD = 0.45


@dataclass(frozen=True)
class TopicBand:
    action: Literal["map", "new", "ask_jev"]
    reason: str


def topic_band(best_similarity: float | None) -> TopicBand:
    if best_similarity is None:
        return TopicBand("new", "First notes for this subject — creating the first topic")
    if best_similarity >= TOPIC_MAP_THRESHOLD:
        return TopicBand("map", f"Strong match to an existing topic (similarity {best_similarity:.2f})")
    if best_similarity < TOPIC_NEW_THRESHOLD:
        return TopicBand("new", f"No similar topic (best similarity {best_similarity:.2f}) — new topic")
    return TopicBand("ask_jev", f"Ambiguous match (similarity {best_similarity:.2f}) — asking a cheap model")
