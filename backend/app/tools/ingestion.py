"""Ingestion agent tools: detect_type, extract_text, check_legibility, run_ocr, vision_transcribe, classify_topic.

Each tool writes its own `ingestion_log` row (path taken, scores, model, tokens, cost, latency).
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Literal

import numpy as np
import pymupdf
from pydantic import BaseModel, Field, create_model
from sqlalchemy import select

from app.agents.base import Tool, ToolContext, ToolError, load_prompt
from app.db.models import ClassSession, IngestionLog, Topic, Upload
from app.ingestion import decisions
from app.ingestion.detect import IMAGE_TYPES, detect_type
from app.ingestion.legibility import check_legibility
from app.ingestion.ocr import encode_png, load_image, run_ocr
from app.llm.embeddings import embed_texts
from app.llm.types import LLMUnavailable
from app.tools.store import create_topic, from_blob, must_get, read_upload_bytes, to_blob

RENDER_DPI = 200


class UploadArg(BaseModel):
    upload_id: str


class PageArg(BaseModel):
    upload_id: str
    page: int | None = Field(default=None, description="1-based PDF page; omit for single images")


class VisionArg(PageArg):
    reason: str = Field(max_length=300)


def _log(ctx: ToolContext, upload_id: str, step: str, path: str, reason: str = "", page: int | None = None,
         **kw: object) -> None:
    ctx.db.add(IngestionLog(upload_id=upload_id, step=step, path_taken=path, reason=reason[:300], page=page, **kw))
    ctx.db.flush()


def _upload(ctx: ToolContext, upload_id: str) -> Upload:
    return must_get(ctx.db, Upload, upload_id, "upload")


def _data(ctx: ToolContext, upload: Upload) -> bytes:
    cache = ctx.state.setdefault("bytes", {})
    if upload.id not in cache:
        cache[upload.id] = read_upload_bytes(upload)
    return cache[upload.id]


def _page_image(ctx: ToolContext, upload: Upload, page: int | None) -> np.ndarray:
    data = _data(ctx, upload)
    if upload.detected_type == "pdf":
        if page is None:
            raise ToolError("page is required for PDFs")
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if not 1 <= page <= doc.page_count:
                raise ToolError(f"page {page} out of range 1..{doc.page_count}")
            pix = doc[page - 1].get_pixmap(dpi=RENDER_DPI)
            return load_image(pix.tobytes("png"))
    return load_image(data)


# ------------------------------------------------------------------ tools
def detect_type_tool(ctx: ToolContext, a: UploadArg) -> dict[str, object]:
    upload = _upload(ctx, a.upload_id)
    t0 = time.monotonic()
    ftype = detect_type(_data(ctx, upload))
    upload.detected_type = ftype
    route = decisions.initial_route(ftype)
    _log(ctx, upload.id, "detect", f"type:{ftype}", f"magic bytes → {ftype}; route {route}",
         latency_ms=int((time.monotonic() - t0) * 1000))
    return {"type": ftype, "route": route}


def extract_text_tool(ctx: ToolContext, a: UploadArg) -> dict[str, object]:
    upload = _upload(ctx, a.upload_id)
    data = _data(ctx, upload)
    pages_text: dict[int, str] = ctx.state.setdefault("pages_text", {})
    t0 = time.monotonic()
    if upload.detected_type == "text":
        text = data.decode("utf-8", errors="replace")
        pages_text[1] = text
        _log(ctx, upload.id, "extract", "plain_text", "typed text upload — no AI needed",
             latency_ms=int((time.monotonic() - t0) * 1000))
        return {"pages": [{"page": 1, "chars": len(text)}]}
    if upload.detected_type != "pdf":
        raise ToolError("extract_text only handles PDFs and plain text; use run_ocr for images")
    out = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text", sort=True)
            pages_text[i] = text
            out.append({"page": i, "chars": len("".join(text.split())), "images": len(page.get_images())})
    _log(ctx, upload.id, "extract", "pymupdf_text_layer", f"{len(out)} page(s) read with PyMuPDF",
         latency_ms=int((time.monotonic() - t0) * 1000), scores={"pages": len(out)})
    return {"pages": out}


def check_legibility_tool(ctx: ToolContext, a: PageArg) -> dict[str, object]:
    upload = _upload(ctx, a.upload_id)
    text = ctx.state.get("pages_text", {}).get(a.page or 1)
    if text is None:
        raise ToolError("call extract_text first")
    report = check_legibility(text)
    decision = decisions.decide_pdf_page(report)
    _log(ctx, upload.id, "legibility", decision.action, decision.reason, page=a.page,
         legibility_score=report.score, scores=report.as_dict())
    return {"passed": report.passed, "action": decision.action, "reason": decision.reason, **report.as_dict()}


async def run_ocr_tool(ctx: ToolContext, a: PageArg) -> dict[str, object]:
    upload = _upload(ctx, a.upload_id)
    if upload.detected_type not in IMAGE_TYPES and upload.detected_type != "pdf":
        raise ToolError(f"cannot OCR a {upload.detected_type} file")
    ctx.db.commit()  # never hold the SQLite write lock during slow OCR
    t0 = time.monotonic()
    img = await asyncio.to_thread(_page_image, ctx, upload, a.page)
    result = await asyncio.to_thread(run_ocr, img)
    decision = decisions.decide_ocr(result)
    ctx.state.setdefault("ocr_text", {})[a.page or 1] = result.text
    _log(ctx, upload.id, "ocr", "local_ocr:" + decision.action, decision.reason, page=a.page,
         ocr_confidence=round(result.mean_confidence, 4), scores={**result.metrics(), "kind": decision.kind},
         model_used="rapidocr-onnx (local)", latency_ms=int((time.monotonic() - t0) * 1000))
    return {"action": decision.action, "kind": decision.kind, "reason": decision.reason, **result.metrics(),
            "preview": result.text[:300]}


async def vision_transcribe_tool(ctx: ToolContext, a: VisionArg) -> dict[str, object]:
    upload = _upload(ctx, a.upload_id)
    img = await asyncio.to_thread(_page_image, ctx, upload, a.page)
    png = await asyncio.to_thread(encode_png, img)
    version, prompt = load_prompt("vision_transcribe")
    ctx.db.commit()
    t0 = time.monotonic()
    try:
        resp = await ctx.llm.chat("vision_transcribe", [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "text", "text": f"Transcribe this page of class notes. Router note: {a.reason}"},
                {"type": "image", "media_type": "image/png", "data": base64.b64encode(png).decode()},
            ]},
        ], ctx=ctx.call_ctx(), reason=f"escalation: {a.reason}")
    except LLMUnavailable as exc:
        fallback = ctx.state.get("ocr_text", {}).get(a.page or 1, "")
        _log(ctx, upload.id, "vision", "vision_unavailable:kept_ocr", f"{a.reason}; no vision model: {exc}"[:300],
             page=a.page, latency_ms=int((time.monotonic() - t0) * 1000))
        ctx.state.setdefault("warnings", []).append(f"page {a.page or 1}: vision model unavailable, kept local OCR")
        return {"markdown": fallback, "degraded": True, "error": str(exc)[:300]}
    md = resp.text.strip()
    ctx.state.setdefault("vision_md", {})[a.page or 1] = md
    _log(ctx, upload.id, "vision", "vision_llm", a.reason, page=a.page, model_used=f"{resp.provider}/{resp.model}",
         tokens_in=resp.input_tokens, tokens_out=resp.output_tokens, cost_usd=resp.cost_usd,
         latency_ms=int((time.monotonic() - t0) * 1000), scores={"prompt": f"vision_transcribe@v{version}"})
    return {"markdown_preview": md[:400], "chars": len(md), "model": f"{resp.provider}/{resp.model}",
            "cost_usd": round(resp.cost_usd, 6)}


# ------------------------------------------------------------------ topic classification (JEV)
def _derive_title(text: str) -> str | None:
    for line in text.splitlines()[:25]:
        s = line.strip().lstrip("#").strip().strip("*_ ").strip()
        if not s:
            continue
        if line.lstrip().startswith("#") and 3 <= len(s) <= 80:
            return s
        if 3 <= len(s) <= 70 and not s.endswith((".", ",", ";", ":")) and len(s.split()) <= 9 and s[0].isupper() \
                and sum(c.isdigit() for c in s) < len(s) / 3:
            return s
    return None


class TopicTitle(BaseModel):
    title: str = Field(min_length=3, max_length=60)


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


async def classify_topic_tool(ctx: ToolContext, a: UploadArg) -> dict[str, object]:
    """Subject is known from the upload/class slot; pick the topic: embeddings first, JEV if ambiguous."""
    upload = _upload(ctx, a.upload_id)
    text = upload.extracted_md
    if not text.strip():
        raise ToolError("upload has no extracted text yet")
    session = ctx.db.get(ClassSession, upload.class_session_id) if upload.class_session_id else None
    _log(ctx, upload.id, "subject", "from_class_slot" if session and session.slot_id else "chosen_by_student",
         "subject known from the class slot — no AI needed" if session and session.slot_id
         else "subject chosen at upload time — no AI needed", scores={"course_id": upload.course_id})

    excerpt = text[:3000]
    ctx.db.commit()
    t0 = time.monotonic()
    vecs, label = await embed_texts([excerpt], ctx.user_id)
    vec = vecs[0]
    topics = list(ctx.db.scalars(select(Topic).where(Topic.course_id == upload.course_id).order_by(Topic.position)))
    stale = [t for t in topics if t.embedding is None or t.embedding_model != label]
    if stale:
        tv, _ = await embed_texts([f"{t.title}\n{t.summary}" for t in stale], ctx.user_id)
        for t, v in zip(stale, tv, strict=True):
            t.embedding, t.embedding_model = to_blob(v), label
    sims = sorted(((_cos(vec, from_blob(t.embedding)), t) for t in topics if t.embedding), key=lambda x: -x[0])
    best = sims[0][0] if sims else None
    band = decisions.topic_band(best)
    method, chosen, cost, tokens_in, tokens_out, model_used = "embedding", None, 0.0, 0, 0, label
    if band.action == "map":
        chosen = sims[0][1]
    elif band.action == "ask_jev":
        candidates = [t for _, t in sims[:6]]
        alias = {f"T{i + 1}": t for i, t in enumerate(candidates)}
        choice_type = Literal[tuple(list(alias) + ["NEW"])]  # type: ignore[valid-type]
        Answer = create_model("TopicAnswer", is_new_topic=(bool, ...), maps_to=(choice_type, ...))  # noqa: N806
        listing = "\n".join(f"{k}: {t.title} — {t.summary[:200]}" for k, t in alias.items())
        try:
            answer, resps = await ctx.llm.structured("jev_classification", [
                {"role": "system", "content": "You classify class notes into existing topics of one subject. "
                                              "Answer only the closed question."},
                {"role": "user", "content": f"Existing topics:\n{listing}\n\nNew notes excerpt:\n{excerpt[:1500]}\n\n"
                                            "Do these notes continue one of the existing topics? "
                                            "maps_to = the topic key, or NEW if they start a new topic. "
                                            "is_new_topic must be true exactly when maps_to is NEW."},
            ], Answer, ctx=ctx.call_ctx(), reason="topic assignment ambiguous (JEV)")
        except LLMUnavailable:
            answer, resps = None, []
        cost = sum(r.cost_usd for r in resps)
        tokens_in, tokens_out = sum(r.input_tokens for r in resps), sum(r.output_tokens for r in resps)
        model_used = f"{resps[-1].provider}/{resps[-1].model}" if resps else None
        consistent = answer is not None and (answer.maps_to == "NEW") == answer.is_new_topic
        if consistent and answer is not None and answer.maps_to != "NEW":
            chosen, method = alias[answer.maps_to], "jev"
        else:
            method = "jev" if consistent else "jev_invalid_default_new"
    title = chosen.title if chosen else None
    if chosen is None:
        title = _derive_title(text)
        if title is None:
            try:
                ans, resps = await ctx.llm.structured("jev_classification", [
                    {"role": "user", "content": f"Give a short topic title (max 60 chars) for these notes:\n{excerpt[:1500]}"},
                ], TopicTitle, ctx=ctx.call_ctx(), reason="new topic has no heading")
            except LLMUnavailable:
                ans, resps = None, []
            cost += sum(r.cost_usd for r in resps)
            title = ans.title if ans else f"Class notes {upload.created_at:%Y-%m-%d}"
        chosen = create_topic(ctx.db, upload.course_id, title)
        chosen.embedding, chosen.embedding_model = to_blob(vec), label
        is_new = True
    else:
        old = from_blob(chosen.embedding) if chosen.embedding else vec
        merged = 0.8 * old + 0.2 * vec
        chosen.embedding = to_blob(merged / (np.linalg.norm(merged) + 1e-9))
        is_new = False
    upload.topic_id = chosen.id
    _log(ctx, upload.id, "topic", f"{method}:{'new' if is_new else 'map'}", band.reason, model_used=model_used,
         tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost, latency_ms=int((time.monotonic() - t0) * 1000),
         scores={"best_similarity": None if best is None else round(best, 3), "topic_id": chosen.id,
                 "candidates": [{"title": t.title, "sim": round(s, 3)} for s, t in sims[:5]]})
    return {"topic_id": chosen.id, "title": chosen.title, "is_new": is_new, "method": method,
            "best_similarity": best, "reason": band.reason}


INGESTION_TOOLS = {
    t.name: t for t in [
        Tool("detect_type", "Detect the upload's file type from magic bytes.", UploadArg, detect_type_tool),
        Tool("extract_text", "Extract the PDF text layer (PyMuPDF) or decode a text file.", UploadArg, extract_text_tool),
        Tool("check_legibility", "Score one page's text layer (density, garbage, dictionary, encoding).", PageArg,
             check_legibility_tool),
        Tool("run_ocr", "Preprocess and OCR an image or rendered PDF page locally; returns confidence metrics.",
             PageArg, run_ocr_tool),
        Tool("vision_transcribe", "Transcribe a page with the cheapest vision model into Markdown + LaTeX.",
             VisionArg, vision_transcribe_tool),
        Tool("classify_topic", "Assign the upload to a topic of its subject (embeddings first, JEV if ambiguous).",
             UploadArg, classify_topic_tool),
    ]
}
