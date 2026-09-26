"""Job handlers: each one drives the journey state machines and dispatches to agents."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select

from app.agents.base import AgentTrace, ToolContext
from app.agents.ingestion import IngestionAgent
from app.agents.llm_agents import CourseMemoryAgent, ExamAgent, NotesAgent
from app.config.brand import get_brand
from app.config.settings import get_settings
from app.db.base import utcnow
from app.db.engine import system_session_ctx
from app.db.models import (
    ClassSession,
    ClassSlot,
    Course,
    Exam,
    ExamPack,
    NoteSection,
    PracticeExam,
    SectionSource,
    Topic,
    Upload,
    User,
)
from app.llm.types import LLMUnavailable
from app.orchestrator.events import emit, once
from app.orchestrator.state_machines import CLASS_SESSION, EXAM_PACK, UPLOAD, transition
from app.orchestrator.timeutil import local_dt, local_today
from app.tools import store
from app.tools.memory import memory_tools
from app.tools.planner import PLANNER_TOOLS

log = logging.getLogger(__name__)


class JobFailed(RuntimeError):
    pass


def _user(user_id: str) -> User:
    with system_session_ctx() as sdb:
        u = sdb.get(User, user_id)
        assert u is not None
        return u


# ------------------------------------------------------------------ class_ended
def ensure_session(ctx: ToolContext, slot: ClassSlot, d: date, tz: str) -> ClassSession:
    s = ctx.db.scalar(select(ClassSession).where(ClassSession.slot_id == slot.id, ClassSession.session_date == d))
    if s is None:
        s = ClassSession(course_id=slot.course_id, slot_id=slot.id, session_date=d,
                         starts_at=local_dt(d, slot.start_time, tz), ends_at=local_dt(d, slot.end_time, tz))
        ctx.db.add(s)
        ctx.db.flush()
    return s


async def handle_class_ended(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    user = _user(ctx.user_id)
    slot = store.must_get(ctx.db, ClassSlot, payload.get("slot_id"), "slot")
    d = date.fromisoformat(payload["session_date"]) if payload.get("session_date") else local_today(ctx.now, user.timezone)
    course = store.must_get(ctx.db, Course, slot.course_id, "course")
    trace = AgentTrace(ctx, "planner", "deterministic", f"Class ended: {course.name} on {d}")
    session = ensure_session(ctx, slot, d, user.timezone)
    if session.state == "scheduled":
        transition(CLASS_SESSION, session, "awaiting_upload")
    trace.decision("session_state", {"session_id": session.id, "state": session.state})
    if session.state == "awaiting_upload":
        await trace.call(PLANNER_TOOLS["create_reminder"], {
            "kind": "upload_prompt", "title": f"{course.name} just ended — upload your notes",
            "body": f"Class of {d.strftime('%A %d %B')} ({slot.start_time}–{slot.end_time}). "
                    f"Upload a PDF, photos or typed text and {get_brand().name} will merge them into your notes.",
            "link": f"/upload?session={session.id}", "data": {"session_id": session.id, "course_id": course.id},
        })
        run_after = (session.ends_at or ctx.now) + timedelta(hours=user.missed_after_hours)
        await trace.call(PLANNER_TOOLS["schedule_job"], {"type": "check_missed_upload",
                                                         "payload": {"session_id": session.id},
                                                         "run_after": run_after.isoformat()})
    trace.finish("succeeded", f"session {session.state}")
    return {"session_id": session.id, "state": session.state}


async def handle_check_missed(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    session = ctx.db.get(ClassSession, payload.get("session_id"))
    if session is None or session.state != "awaiting_upload":
        return {"skipped": True, "state": getattr(session, "state", None)}
    if once(ctx.db, f"missed:{session.id}"):
        emit(ctx.db, "class_slot_passed_without_upload", {"session_id": session.id}, "scheduler")
    return {"emitted": True}


async def handle_missed_upload(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Course Memory agent, deterministic handler: flag the session and remind the student."""
    session = store.must_get(ctx.db, ClassSession, payload.get("session_id"), "session")
    course = store.must_get(ctx.db, Course, session.course_id, "course")
    ctx.state["course_id"] = course.id
    trace = AgentTrace(ctx, "course_memory", "deterministic", f"Missed notes: {course.name} {session.session_date}")
    if session.state != "awaiting_upload":
        trace.finish("succeeded", f"nothing to do (session is {session.state})")
        return {"skipped": True}
    flag = {t.name: t for t in memory_tools()}["flag_missed_session"]
    await trace.call(flag, {"session_id": session.id, "reason": "no notes uploaded after the class"})
    await trace.call(PLANNER_TOOLS["create_reminder"], {
        "kind": "reminder", "title": f"No notes yet for {course.name} ({session.session_date:%a %d %b})",
        "body": "This class is flagged as missed in your course memory. Upload notes (yours or a classmate's) "
                "whenever you can — the flag clears automatically.",
        "link": f"/upload?session={session.id}", "data": {"session_id": session.id, "course_id": course.id},
    })
    trace.finish("succeeded", "session flagged as missed")
    return {"session_id": session.id, "state": session.state}


# ------------------------------------------------------------------ upload pipeline
def _set_upload(ctx: ToolContext, upload: Upload, state: str | None = None, msg: str | None = None) -> None:
    if state:
        transition(UPLOAD, upload, state)
    if msg:
        upload.status_message = msg[:300]
    ctx.db.commit()


def _session_for_upload(ctx: ToolContext, upload: Upload) -> ClassSession:
    if upload.class_session_id:
        s = ctx.db.get(ClassSession, upload.class_session_id)
        if s is not None:
            return s
    tz = _user(ctx.user_id).timezone
    d = local_today(upload.created_at, tz)
    s = ctx.db.scalar(select(ClassSession).where(ClassSession.course_id == upload.course_id,
                                                ClassSession.session_date == d)
                      .order_by(ClassSession.created_at))
    if s is None:
        s = ClassSession(course_id=upload.course_id, slot_id=None, session_date=d, state="scheduled")
        ctx.db.add(s)
        ctx.db.flush()
    upload.class_session_id = s.id
    return s


async def handle_process_upload(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    upload = store.must_get(ctx.db, Upload, payload.get("upload_id"), "upload")
    ctx.state.update(course_id=upload.course_id, upload_id=upload.id)
    ctx.progress = lambda msg: _set_upload(ctx, upload, msg=msg)  # live, plain-language status for the UI
    warnings: list[str] = []
    try:
        _set_upload(ctx, upload, "extracting", "Starting…")
        agent = IngestionAgent()
        result = await agent.run(ctx, upload, on_classify=lambda: _set_upload(ctx, upload, "classifying"))
        warnings += result.warnings
        if upload.state == "extracting":
            _set_upload(ctx, upload, "classifying")
        session = _session_for_upload(ctx, upload)
        if CLASS_SESSION.can(session.state, "uploaded"):
            transition(CLASS_SESSION, session, "uploaded")
        if upload.kind == "past_exam":
            _set_upload(ctx, upload, "done", "Past exam stored — used as style reference for practice exams")
            return {"upload_id": upload.id, "kind": "past_exam"}

        # --- Notes agent
        _set_upload(ctx, upload, "structuring", f"Merging into your notes on “{result.topic_title}”…")
        notes_summary = await _run_notes(ctx, upload, result.topic_id, result.topic_title, result.topic_is_new,
                                         warnings)

        # --- Course Memory agent
        _set_upload(ctx, upload, "updating_memory", "Updating course memory…")
        await _run_memory(ctx, upload, session, notes_summary, warnings)
        if CLASS_SESSION.can(session.state, "processed"):
            transition(CLASS_SESSION, session, "processed")
        done_msg = f"Done — merged into “{result.topic_title}”" + (" (with warnings)" if warnings else "")
        _set_upload(ctx, upload, "done", done_msg)
        course = ctx.db.get(Course, upload.course_id)
        await PLANNER_TOOLS["create_reminder"].invoke(ctx, {
            "kind": "info", "title": f"Notes merged: {course.name if course else ''} → {result.topic_title}",
            "body": notes_summary[:500] + ("\n\nWarnings: " + "; ".join(warnings) if warnings else ""),
            "link": f"/subjects/{upload.course_id}?topic={result.topic_id}"})
        ctx.db.commit()
        return {"upload_id": upload.id, "topic_id": result.topic_id, "llm_pages": result.llm_pages,
                "warnings": warnings}
    except Exception as exc:
        ctx.db.rollback()
        upload = store.must_get(ctx.db, Upload, payload.get("upload_id"), "upload")
        upload.error = f"{type(exc).__name__}: {exc}"[:2000]
        if UPLOAD.can(upload.state, "failed"):
            transition(UPLOAD, upload, "failed")
        upload.status_message = "Failed — " + str(exc)[:250]
        ctx.db.commit()
        raise


async def _run_notes(ctx: ToolContext, upload: Upload, topic_id: str | None, topic_title: str | None,
                     is_new: bool, warnings: list[str]) -> str:
    topics = list(ctx.db.scalars(select(Topic).where(Topic.course_id == upload.course_id)))
    goal = (f"UPLOAD id={upload.id} file={upload.filename!r} uploaded {upload.created_at:%Y-%m-%d}\n"
            f"ASSIGNED TOPIC id={topic_id} title={topic_title!r} ({'new, empty' if is_new else 'existing'})\n"
            f"OTHER TOPICS IN THIS SUBJECT: " + ", ".join(f"{t.title} [{t.id}]" for t in topics if t.id != topic_id)
            + f"\n\nNEW CONTENT (Markdown):\n{upload.extracted_md[:30000]}")
    summary = ""
    try:
        res = await NotesAgent().run(ctx, goal)
        if res.state == "succeeded" and isinstance(res.terminal_result, dict):
            summary = str(res.terminal_result.get("summary", ""))
        else:
            warnings.append(f"notes agent ended with state {res.state}")
    except LLMUnavailable as exc:
        warnings.append(f"notes model unavailable ({exc.errors[0][:120] if exc.errors else exc})")
    linked = ctx.db.scalar(select(func.count()).select_from(SectionSource)
                           .where(SectionSource.upload_id == upload.id)) or 0
    if not linked and topic_id:
        # Deterministic fallback so the content is never lost: append it verbatim, with its source.
        topic = store.must_get(ctx.db, Topic, topic_id, "topic")
        section = store.append_section(ctx.db, topic, f"Notes from {upload.created_at:%d %b %Y} ({upload.filename})",
                                       upload.extracted_md, [upload.id])
        await store.reindex_section(ctx.db, ctx.user_id, section)
        warnings.append("notes were added verbatim (agent fallback)")
        summary = summary or f"Added the upload verbatim to {topic.title}."
    ctx.db.commit()
    return summary or f"Merged {upload.filename} into {topic_title}."


async def _run_memory(ctx: ToolContext, upload: Upload, session: ClassSession, notes_summary: str,
                      warnings: list[str]) -> None:
    ctx.state["require_summary"] = True
    touched = sorted({s.topic_id for s in ctx.db.scalars(
        select(NoteSection).join(SectionSource, SectionSource.section_id == NoteSection.id)
        .where(SectionSource.upload_id == upload.id))})
    goal = (f"SESSION id={session.id} date={session.session_date.isoformat()} state={session.state}\n"
            f"TOPICS TOUCHED: {touched}\nNOTES AGENT SUMMARY: {notes_summary}\n\n"
            f"UPLOAD EXCERPT:\n{upload.extracted_md[:6000]}")
    try:
        res = await CourseMemoryAgent().run(ctx, goal)
        if res.state != "succeeded":
            warnings.append(f"course memory agent ended with state {res.state}")
    except LLMUnavailable as exc:
        warnings.append(f"course memory model unavailable ({exc.errors[0][:120] if exc.errors else exc})")
    if not session.summary_md.strip():
        session.summary_md = notes_summary  # deterministic minimum: the session always records what was covered
    session.topic_ids = sorted(set(session.topic_ids) | set(touched))
    ctx.db.commit()


# ------------------------------------------------------------------ exam packs
async def handle_build_exam_pack(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    exam = ctx.db.get(Exam, payload["exam_id"]) if payload.get("exam_id") else None
    course_id = exam.course_id if exam else payload.get("course_id")
    course = store.must_get(ctx.db, Course, course_id, "course")
    n_sections = ctx.db.scalar(select(func.count()).select_from(NoteSection)
                               .where(NoteSection.course_id == course.id)) or 0
    if not n_sections:
        raise JobFailed(f"No notes yet for {course.name}: upload class notes before building an exam pack.")
    prev_version = ctx.db.scalar(select(func.max(ExamPack.version)).where(
        ExamPack.course_id == course.id, ExamPack.exam_id == (exam.id if exam else None))) or 0
    trigger = f"T-{payload['threshold']}" if payload.get("threshold") else payload.get("source", "manual")
    pack = ExamPack(course_id=course.id, exam_id=exam.id if exam else None, version=prev_version + 1,
                    trigger=str(trigger), notes_cutoff=utcnow(), job_id=ctx.job_id)
    ctx.db.add(pack)
    ctx.db.flush()
    for n in range(1, s.EXAM_PACK_PRACTICE_EXAMS + 1):
        ctx.db.add(PracticeExam(pack_id=pack.id, number=n, title=f"Practice exam {n}"))
    transition(EXAM_PACK, pack, "building")
    ctx.db.commit()
    ctx.state.update(pack_id=pack.id, course_id=course.id, n_exams=s.EXAM_PACK_PRACTICE_EXAMS,
                     n_questions=s.EXAM_PACK_QUESTIONS_PER_EXAM)
    ctx.progress(f"Building exam pack v{pack.version} for {course.name}…")
    goal = (f"Build Exam Pack v{pack.version} for subject {course.name!r}"
            + (f", exam {exam.title!r} on {exam.exam_date.isoformat()}" if exam else " (on-demand practice exam)")
            + f". Trigger: {trigger}. Requirements: {s.EXAM_PACK_PRACTICE_EXAMS} practice exams × "
              f"{s.EXAM_PACK_QUESTIONS_PER_EXAM} verified questions, plus a study guide. Start with get_exam_scope.")
    try:
        res = await ExamAgent().run(ctx, goal)
    except Exception as exc:
        ctx.db.rollback()
        _fail_pack(ctx, pack.id, f"{type(exc).__name__}: {exc}")
        raise
    pack = store.must_get(ctx.db, ExamPack, pack.id, "exam pack")
    if res.finished_by != "save_exam_pack" or pack.state != "ready":
        _fail_pack(ctx, pack.id, f"exam agent ended with state {res.state} before saving the pack")
        raise JobFailed(f"Exam agent did not complete the pack (state {res.state})")
    await PLANNER_TOOLS["create_reminder"].invoke(ctx, {
        "kind": "exam_pack", "title": f"Exam Pack ready: {exam.title if exam else course.name} (v{pack.version})",
        "body": f"Study guide + {s.EXAM_PACK_PRACTICE_EXAMS} practice exams with solutions, built from your notes.",
        "link": f"/packs/{pack.id}", "data": {"pack_id": pack.id}})
    ctx.db.commit()
    return {"pack_id": pack.id, "version": pack.version}


def _fail_pack(ctx: ToolContext, pack_id: str, error: str) -> None:
    pack = ctx.db.get(ExamPack, pack_id)
    if pack is not None and EXAM_PACK.can(pack.state, "failed"):
        transition(EXAM_PACK, pack, "failed")
        pack.error = error[:2000]
        ctx.db.commit()


HANDLERS = {
    "class_ended": handle_class_ended,
    "check_missed_upload": handle_check_missed,
    "missed_upload": handle_missed_upload,
    "process_upload": handle_process_upload,
    "build_exam_pack": handle_build_exam_pack,
}
