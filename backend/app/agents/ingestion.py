"""Ingestion agent: runs the deterministic-first router with its toolset (DECISIONS D-05).

Policy (code, not a prompt):
  detect_type ─┬─ pdf ──▶ extract_text ─▶ per page check_legibility ─┬─ pass ─▶ keep text layer
               │                                                     └─ fail ─▶ run_ocr ─▶ (vision_transcribe)
               ├─ image ─▶ run_ocr ─┬─ clean prose ─▶ keep OCR text
               │                    └─ low conf / handwriting / equations / diagrams ─▶ vision_transcribe
               └─ text ──▶ extract_text
  then (notes only) classify_topic: subject from the class slot, topic via embeddings, JEV if ambiguous.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.agents.base import AgentTrace, ToolContext
from app.db.models import Upload
from app.tools.ingestion import INGESTION_TOOLS as T


class IngestionFailed(RuntimeError):
    pass


@dataclass
class IngestionResult:
    markdown: str
    topic_id: str | None
    topic_title: str | None
    topic_is_new: bool
    llm_pages: int
    warnings: list[str] = field(default_factory=list)


class IngestionAgent:
    name = "ingestion"

    async def run(self, ctx: ToolContext, upload: Upload,
                  on_classify: Callable[[], None] = lambda: None) -> IngestionResult:
        trace = AgentTrace(ctx, self.name, "deterministic", f"Ingest {upload.filename}")
        try:
            result = await self._run(ctx, trace, upload, on_classify)
        except Exception as exc:
            ctx.db.rollback()
            trace.finish("failed", error=f"{type(exc).__name__}: {exc}")
            raise
        trace.finish("succeeded", f"{len(result.markdown)} chars; topic={result.topic_title}; "
                                  f"vision pages={result.llm_pages}")
        return result

    async def _run(self, ctx: ToolContext, trace: AgentTrace, upload: Upload,
                   on_classify: Callable[[], None]) -> IngestionResult:
        uid = {"upload_id": upload.id}
        ctx.progress("Detecting file type…")
        det = await trace.call(T["detect_type"], uid)
        route = det["route"]
        page_md: dict[int, str] = {}
        llm_pages = 0

        async def ocr_then_maybe_vision(page: int | None) -> None:
            nonlocal llm_pages
            ctx.progress(f"{'Page ' + str(page) + ': ' if page else ''}running local OCR…")
            ocr = await trace.call(T["run_ocr"], {**uid, "page": page})
            if ocr["action"] == "accept_ocr":
                ctx.progress(ocr["reason"])
                page_md[page or 1] = ctx.state["ocr_text"][page or 1]
                return
            ctx.progress(ocr["reason"])
            trace.decision("escalate_to_vision", {"page": page, "reason": ocr["reason"], "kind": ocr["kind"]})
            res = await trace.call(T["vision_transcribe"], {**uid, "page": page, "reason": ocr["reason"]})
            if res.get("degraded"):
                page_md[page or 1] = res["markdown"]
            else:
                llm_pages += 1
                page_md[page or 1] = ctx.state["vision_md"][page or 1]

        if route == "unsupported":
            raise IngestionFailed(f"Unsupported file type ({det['type']}). Upload a PDF, an image or a text file.")
        if route == "plain_text":
            await trace.call(T["extract_text"], uid)
            ctx.progress("Typed text — no AI needed")
            page_md[1] = ctx.state["pages_text"][1]
        elif route == "text_layer":
            ctx.progress("Reading the PDF text layer…")
            pages = (await trace.call(T["extract_text"], uid))["pages"]
            for p in pages:
                n = p["page"]
                leg = await trace.call(T["check_legibility"], {**uid, "page": n})
                if leg["passed"]:
                    page_md[n] = ctx.state["pages_text"][n]
                    ctx.progress(f"Page {n}: Text layer found — no AI needed")
                else:
                    trace.decision("page_needs_ocr", {"page": n, "reason": leg["reason"]})
                    await ocr_then_maybe_vision(n)
        else:  # image
            await ocr_then_maybe_vision(None)

        markdown = "\n\n".join(page_md[k].strip() for k in sorted(page_md) if page_md[k].strip())
        if not markdown.strip():
            raise IngestionFailed("No readable content found in this file.")
        upload.extracted_md = markdown
        ctx.db.flush()

        topic_id = topic_title = None
        topic_new = False
        on_classify()
        if upload.kind == "notes":
            ctx.progress("Assigning the topic…")
            topic = await trace.call(T["classify_topic"], uid)
            topic_id, topic_title, topic_new = topic["topic_id"], topic["title"], topic["is_new"]
            ctx.progress(f"Topic: {topic_title}{' (new)' if topic_new else ''}")
        return IngestionResult(markdown, topic_id, topic_title, topic_new, llm_pages,
                               list(ctx.state.get("warnings", [])))
