"""Timetable extraction pipeline (onboarding step 1, UX.md §8). Deterministic first, then the cheap model.

    .ics file / link ─▶ parse_ics                                      (no LLM)
    pasted text ────▶ parse_text ──(nothing found)──▶ LLM text        (timetable_extraction)
    PDF with text ──▶ words ─▶ parse_grid ──(low confidence)──▶ vision (page image)
    scanned PDF / image ─▶ local OCR boxes ─▶ parse_grid ──(low confidence)──▶ vision
    every result ───▶ typed validation (SlotOut: weekday 0-6, HH:MM, 15 min ≤ length ≤ 6 h) + overlap check

Every decision is recorded in an `onboarding` agent trace, so the UI can stream it.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from typing import Literal
from urllib.parse import urlparse

import httpx
import numpy as np
from pydantic import BaseModel, Field

from app.agents.base import AgentTrace, ToolContext, load_prompt
from app.ingestion.detect import detect_type
from app.ingestion.ocr import encode_png, load_image, ocr_items
from app.llm.types import LLMUnavailable, Message
from app.onboarding.timetable import (
    GRID_ACCEPT,
    LOW_CONFIDENCE,
    Extraction,
    SlotOut,
    Token,
    dedupe,
    overlaps,
    parse_grid,
    parse_ics,
    parse_text,
)

MAX_ICS_BYTES = 2_000_000
_DAY = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


class ExtractionError(ValueError):
    """User-facing reason the input could not be read."""


class LLMSlot(BaseModel):
    subject: str = Field(max_length=120)
    weekday: Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    start: str = Field(description="HH:MM, 24-hour")
    end: str = Field(description="HH:MM, 24-hour")
    room: str = Field(default="", max_length=120)
    professor: str = Field(default="", max_length=160)
    certainty: Literal["certain", "unsure"]


class LLMTimetable(BaseModel):
    slots: list[LLMSlot] = Field(default_factory=list, max_length=80)


# ------------------------------------------------------------------ URL fetch (SSRF-guarded)
def _public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ExtractionError(f"Couldn't reach {host}.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ExtractionError("That link points to a private network address, so I won't fetch it.")


async def fetch_ics(url: str) -> bytes:
    url = url.strip().replace("webcal://", "https://", 1)
    for _ in range(4):  # follow redirects by hand so every hop is checked
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ExtractionError("Paste an http(s) or webcal calendar link.")
        await asyncio.to_thread(_public_host, parsed.hostname)
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            async with client.stream("GET", url) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    url = str(resp.url.join(resp.headers["location"]))
                    continue
                if resp.status_code != 200:
                    raise ExtractionError(f"The calendar link answered HTTP {resp.status_code}.")
                data = b""
                async for chunk in resp.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_ICS_BYTES:
                        raise ExtractionError("That calendar is larger than 2 MB.")
                return data
    raise ExtractionError("Too many redirects.")


# ------------------------------------------------------------------ token sources
def _pdf_tokens(data: bytes) -> tuple[list[Token], np.ndarray, bool]:
    """Words from the first page's text layer (+ rendered page for colours). Falls back to OCR for scans."""
    import cv2
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        if doc.page_count == 0:
            raise ExtractionError("The PDF has no pages.")
        page, z = doc[0], 2.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z))
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        words = page.get_text("words")
    finally:
        doc.close()
    if len(words) >= 6:
        return [Token(w[4], w[0] * z, w[1] * z, w[2] * z, w[3] * z) for w in words], img, True
    toks, color = _ocr_tokens(img)
    return toks, color, False


def _ocr_tokens(img: np.ndarray) -> tuple[list[Token], np.ndarray]:
    items, color, _ = ocr_items(img)
    return [Token(t, float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 0].max()), float(b[:, 1].max()), s)
            for b, t, s in items], color


# ------------------------------------------------------------------ LLM fallback
async def _llm(ctx: ToolContext, trace: AgentTrace, reason: str, image_png: bytes | None, text: str | None
               ) -> list[SlotOut] | None:
    version, prompt = load_prompt("timetable_extraction")
    trace.decision("escalate_timetable", {"reason": reason, "input": "image" if image_png else "text",
                                          "prompt": f"timetable_extraction@v{version}"})
    content: list[dict[str, str]] = [{"type": "text", "text": "Extract the weekly timetable." if image_png
                                      else f"Extract the weekly timetable from this text:\n\n{(text or '')[:8000]}"}]
    if image_png:
        content.append({"type": "image", "media_type": "image/png", "data": base64.b64encode(image_png).decode()})
    messages: list[Message] = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]  # type: ignore[list-item]
    ctx.db.commit()
    try:
        result, resps = await ctx.llm.structured("timetable_extraction", messages, LLMTimetable, ctx=ctx.call_ctx(),
                                                 reason=f"timetable: {reason}")
    except LLMUnavailable as exc:
        trace.step("tool", "extract_timetable", {"via": "llm"}, {"error": str(exc)[:300]}, ok=False)
        return None
    for r in resps:
        trace.llm(r)
    if result is None:
        trace.step("tool", "extract_timetable", {"via": "llm"}, {"error": "invalid output twice"}, ok=False)
        return None
    slots, dropped = [], 0
    for s in result.slots:
        c = 0.9 if s.certainty == "certain" else 0.6
        try:
            slots.append(SlotOut(subject=s.subject, weekday=_DAY[s.weekday], start=s.start, end=s.end, room=s.room,
                                 professor=s.professor,
                                 confidence={"subject": c, "time": c, "room": c if s.room else 1.0,
                                             "professor": c if s.professor else 1.0}))
        except ValueError:
            dropped += 1  # typed validation: impossible times etc. are discarded, not guessed
    trace.step("tool", "extract_timetable", {"via": "llm"},
               {"summary": f"{len(slots)} classes", "dropped_invalid": dropped})
    return slots


# ------------------------------------------------------------------ pipeline
async def extract_timetable(ctx: ToolContext, *, data: bytes | None = None, text: str | None = None,
                            url: str | None = None, tz: str = "Europe/Madrid") -> Extraction:
    trace = AgentTrace(ctx, "onboarding", "deterministic", "Read your timetable")
    warnings: list[str] = []
    method: str = "none"
    slots: list[SlotOut] = []
    exams = []
    grid_conf = 1.0
    try:
        if url:
            data = await fetch_ics(url)
            trace.step("tool", "fetch_calendar", {"host": urlparse(url).hostname}, {"bytes": len(data)})
        if data is None and text is not None:
            data = text.encode()
        if not data or not data.strip():
            raise ExtractionError("Drop a screenshot, photo, PDF or .ics file, or paste your timetable.")
        kind = detect_type(data)
        trace.step("tool", "detect_type", {"bytes": len(data)}, {"type": kind})
        if kind == "text":
            body = data.decode("utf-8", errors="replace")
            if "BEGIN:VCALENDAR" in body[:2000]:
                slots, exams, warnings = parse_ics(body, tz)
                method = "ics"
                trace.step("tool", "parse_timetable", {"format": "ics"},
                           {"summary": f"{len(slots)} weekly classes, {len(exams)} exam dates"})
            else:
                slots = parse_text(body)
                method = "text"
                trace.step("tool", "parse_timetable", {"format": "text"}, {"summary": f"{len(slots)} classes"})
                if not slots:
                    got = await _llm(ctx, trace, "no 'day + time range' lines found in the text", None, body)
                    slots, method = got or [], "llm_text"
        elif kind in ("pdf", "png", "jpeg", "heic", "webp", "tiff"):
            if kind == "pdf":
                tokens, img, has_text = await asyncio.to_thread(_pdf_tokens, data)
                trace.step("tool", "extract_text", {"format": "pdf"},
                           {"source": "text layer" if has_text else "local OCR", "tokens": len(tokens)})
            else:
                img = load_image(data)
                tokens, img = await asyncio.to_thread(_ocr_tokens, img)
                trace.step("tool", "run_ocr", {"format": kind}, {"action": "grid", "tokens": len(tokens),
                                                                 "reason": f"{len(tokens)} text boxes found"})
            grid = parse_grid(tokens, img)
            grid_conf = grid.confidence
            trace.decision("grid_parse", {"slots": len(grid.slots), "confidence": grid.confidence,
                                          "reason": grid.reason, **grid.stats})
            slots, method = grid.slots, "grid"
            if grid.confidence < GRID_ACCEPT:
                got = await _llm(ctx, trace, f"grid parser not confident ({grid.confidence:.2f}): {grid.reason}",
                                 encode_png(img, max_side=2000), None)
                if got:
                    slots, method = got, "vision"
                elif grid.slots:
                    warnings.append("The AI reader was unavailable; showing what I could read myself — check it.")
        else:
            raise ExtractionError("I can read screenshots, photos, PDFs, .ics calendars or pasted text.")
    except ExtractionError as exc:
        trace.finish("failed", error=str(exc))
        raise
    slots = dedupe(slots)
    for a, b in overlaps(slots):
        warnings.append(f"{a.subject} and {b.subject} overlap on the same day — check the times.")
        for s in (a, b):
            s.confidence["time"] = min(s.confidence.get("time", 1.0), 0.6)
    low = sum(1 for s in slots for v in s.confidence.values() if v < LOW_CONFIDENCE)
    trace.step("tool", "validate_timetable", {}, {"slots": len(slots), "low_confidence": low})
    confidence = grid_conf if method == "grid" else (0.85 if method in ("vision", "llm_text") else 1.0 if slots else 0.0)
    if not slots:
        warnings.append("I couldn't find any classes here. Try another picture, the PDF, or paste it as text.")
    trace.finish("succeeded" if slots else "failed", f"{len(slots)} classes via {method}",
                 error="" if slots else "no classes found")
    return Extraction(slots=slots, exams=exams, method=method, confidence=round(confidence, 2),  # type: ignore[arg-type]
                      warnings=warnings, run_id=trace.run.id)
