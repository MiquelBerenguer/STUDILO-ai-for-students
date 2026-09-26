"""Job handlers: each one drives the journey state machines and dispatches to agents."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agents.base import AgentTrace, ToolContext, load_prompt
from app.agents.ingestion import IngestionAgent
from app.agents.llm_agents import CourseMemoryAgent, ExamAgent, NotesAgent, QAAgent
from app.config.brand import get_brand
from app.config.settings import get_settings
from app.db.base import utcnow
from app.db.engine import system_session_ctx
from app.db.models import (
    ClassSession,
    ClassSlot,
    Course,
    CourseMemory,
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
from app.orchestrator import actions, cards
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
            "kind": "upload_prompt", "title": f"Your {course.name} class ended — drop your notes here",
            "body": f"Class of {d.strftime('%A %d %B')} ({slot.start_time}–{slot.end_time}). A PDF, photos or typed "
                    f"text: {get_brand().name} files them into your notes.",
            "link": f"/upload?session={session.id}",
            "data": {"session_id": session.id, "course_id": course.id,
                     "ends_at": session.ends_at.isoformat() if session.ends_at else None},
            "actions": [cards.action("drop_notes", "Drop notes", "upload", primary=True,
                                     params={"course_id": course.id, "class_session_id": session.id, "kind": "notes"}),
                        cards.action("dismiss", "Not today")],
            "dedupe_key": f"upload_prompt:{session.id}",
        })
        asked = cards.ask_exam_date(ctx.db, course)
        if asked is not None:
            trace.decision("ask_exam_date", {"course": course.name, "card_id": asked.id})
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
    cards.resolve_matching(ctx.db, ("upload_prompt",), session_id=session.id)
    await trace.call(PLANNER_TOOLS["create_reminder"], {
        "kind": "missed_class", "title": f"You missed {session.session_date:%A}'s {course.name} class",
        "body": "No notes arrived, so I flagged it in your course memory. Want a catch-up from your notes and the "
                "syllabus? Late notes (yours or a classmate's) clear the flag.",
        "link": f"/upload?session={session.id}", "data": {"session_id": session.id, "course_id": course.id},
        "actions": [cards.action("catch_up", "Catch me up", primary=True),
                    cards.action("drop_notes", "Upload late notes", "upload",
                                 params={"course_id": course.id, "class_session_id": session.id, "kind": "notes"}),
                    cards.action("dismiss", "Dismiss")],
        "dedupe_key": f"missed_class:{session.id}",
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
        effects = store.fx(ctx.state)
        effects.update(actions.snapshot_session_and_memory(ctx.db, session, upload.course_id), upload_id=upload.id)
        if CLASS_SESSION.can(session.state, "uploaded"):
            transition(CLASS_SESSION, session, "uploaded")
        if upload.kind == "past_exam":
            _set_upload(ctx, upload, "done", "Past exam stored — used as style reference for practice exams")
            cards.resolve_matching(ctx.db, ("past_exams_wanted",), course_id=upload.course_id)
            ctx.db.commit()
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
        course = store.must_get(ctx.db, Course, upload.course_id, "course")
        how = ("handwriting/equations — transcribed with AI" if result.llm_pages else "text was clear — no AI needed to read it")
        title = f"Filed {upload.filename} into {result.topic_title}"
        act = actions.record_file_notes(ctx.db, upload, ctx.job_id, dict(effects), title)
        cards.create_card(
            ctx.db, "notes_filed", title,
            body=f"{how[0].upper()}{how[1:]}. Updated your {course.name} course memory. " + notes_summary[:400]
                 + ("\n\nWarnings: " + "; ".join(warnings) if warnings else ""),
            link=f"/subjects/{upload.course_id}?topic={result.topic_id}",
            actions=[cards.action("open", "Open notes", "link", primary=True,
                                  href=f"/subjects/{upload.course_id}?topic={result.topic_id}"),
                     cards.action("undo", "Undo")],
            data={"upload_id": upload.id, "course_id": course.id, "topic_id": result.topic_id,
                  "llm_pages": result.llm_pages}, action_id=act.id, course_id=course.id)
        cards.ask_syllabus(ctx.db, course)
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
        store.fx(ctx.state)["created_sections"].append(section.id)
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
    # On-demand requests from the command bar ("make me a 1h exam on entropy") carry focus + duration.
    focus = str(payload.get("focus") or "").strip()[:120]
    duration = int(payload["duration_minutes"]) if payload.get("duration_minutes") else None
    n_exams = int(payload.get("n_exams") or s.EXAM_PACK_PRACTICE_EXAMS)
    n_questions = max(2, min(8, duration // 20)) if duration else s.EXAM_PACK_QUESTIONS_PER_EXAM
    for n in range(1, n_exams + 1):
        ctx.db.add(PracticeExam(pack_id=pack.id, number=n, title=f"Practice exam {n}", duration_minutes=duration or 90))
    transition(EXAM_PACK, pack, "building")
    ctx.db.commit()
    ctx.state.update(pack_id=pack.id, course_id=course.id, n_exams=n_exams, n_questions=n_questions, focus=focus,
                     duration_minutes=duration)
    ctx.progress(f"Building exam pack v{pack.version} for {course.name}…")
    goal = (f"Build Exam Pack v{pack.version} for subject {course.name!r}"
            + (f", exam {exam.title!r} on {exam.exam_date.isoformat()}" if exam else " (on-demand practice exam)")
            + f". Trigger: {trigger}. Requirements: {n_exams} practice exam(s) × "
              f"{n_questions} verified questions, plus a study guide."
            + (f" FOCUS the questions and the guide on: {focus}." if focus else "")
            + (f" Each practice exam must take about {duration} minutes." if duration else "")
            + " Start with get_exam_scope.")
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
    if exam:
        days = (exam.exam_date - local_today(ctx.now, _user(ctx.user_id).timezone)).days
        title = (f"{exam.title} in {days} days. I refreshed your Exam Pack with this week's notes." if pack.version > 1
                 else f"{exam.title} in {days} days. I built your Exam Pack.")
    elif focus or duration:
        title = f"Your {f'{duration}-min ' if duration else ''}{course.name} exam{f' on {focus}' if focus else ''} is ready."
    else:
        title = f"Your {course.name} practice exam is ready."
    act = actions.record_pack(ctx.db, pack, ctx.job_id, title)
    cards.create_card(
        ctx.db, "exam_pack_ready", title,
        body=f"Study guide + {n_exams} practice exam(s) with worked solutions, each question verified against "
             "your notes.",
        link=f"/packs/{pack.id}", data={"pack_id": pack.id, "exam_id": exam.id if exam else None},
        actions=[cards.action("open", "Open pack", "link", primary=True, href=f"/packs/{pack.id}"),
                 cards.action("undo", "Undo")], action_id=act.id, course_id=course.id)
    ctx.db.commit()
    return {"pack_id": pack.id, "version": pack.version}


def _fail_pack(ctx: ToolContext, pack_id: str, error: str) -> None:
    pack = ctx.db.get(ExamPack, pack_id)
    if pack is not None and EXAM_PACK.can(pack.state, "failed"):
        transition(EXAM_PACK, pack, "failed")
        pack.error = error[:2000]
        ctx.db.commit()


# ------------------------------------------------------------------ catch-up (missed class)
class CatchUp(BaseModel):
    likely_topics: list[str] = Field(default_factory=list, max_length=4)
    summary_md: str = Field(min_length=1, max_length=4000)
    cited_section_ids: list[str] = Field(default_factory=list, max_length=12)


async def handle_catch_up(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    """One structured LLM call grounded in syllabus, memory and existing notes; the result is a feed card."""
    session = store.must_get(ctx.db, ClassSession, payload.get("session_id"), "session")
    course = store.must_get(ctx.db, Course, session.course_id, "course")
    sections = list(ctx.db.scalars(select(NoteSection).where(NoteSection.course_id == course.id)
                                   .order_by(NoteSection.updated_at.desc()).limit(25)))
    if not sections and not course.syllabus.strip():
        raise JobFailed(f"I don't have notes or a syllabus for {course.name} yet, so I can't guess what was covered. "
                        "Paste the syllabus or upload a classmate's notes.")
    version, prompt = load_prompt("catch_up")
    trace = AgentTrace(ctx, "catch_up", "llm", f"Catch-up for {course.name} on {session.session_date:%a %d %b}",
                       task="course_memory", prompt_version=f"catch_up@v{version}")
    around = list(ctx.db.scalars(select(ClassSession).where(ClassSession.course_id == course.id,
                                                            ClassSession.id != session.id)
                                 .order_by(ClassSession.session_date)))
    before = [x for x in around if x.session_date < session.session_date][-2:]
    after = [x for x in around if x.session_date > session.session_date][:2]
    mem = ctx.db.scalar(select(CourseMemory).where(CourseMemory.course_id == course.id))
    material = (
        f"COURSE: {course.name}\nMISSED CLASS: {session.session_date:%A %d %B %Y}\n"
        f"SYLLABUS:\n{course.syllabus[:3000] or '(none)'}\n"
        f"COURSE MEMORY: {mem.syllabus_position if mem else ''} {mem.pace_note if mem else ''}\n"
        + "".join(f"CLASS BEFORE ({x.session_date}): {x.summary_md[:600]}\n" for x in before)
        + "".join(f"CLASS AFTER ({x.session_date}): {x.summary_md[:600]}\n" for x in after)
        + "NOTE SECTIONS:\n" + "".join(f"[{x.id}] {x.heading}: {x.content_md[:500]}\n" for x in sections))
    trace.step("tool", "gather_material", {"session_id": session.id},
               {"sections": len(sections), "classes_before": len(before), "classes_after": len(after),
                "has_syllabus": bool(course.syllabus.strip())})
    ctx.db.commit()
    result, resps = await ctx.llm.structured("course_memory", [{"role": "system", "content": prompt},
                                                               {"role": "user", "content": material}],
                                             CatchUp, ctx=ctx.call_ctx(), reason="catch-up for a missed class")
    for r in resps:
        trace.llm(r)
    if result is None:
        trace.finish("failed", error="model returned invalid output twice")
        raise JobFailed("The model returned an invalid catch-up twice.")
    valid_ids = {x.id for x in sections}
    cited = [sid for sid in result.cited_section_ids if sid in valid_ids]
    topics_txt = ", ".join(result.likely_topics) or "nothing I can tell from your material"
    card = cards.create_card(
        ctx.db, "catch_up_ready", f"Catch-up for {course.name}, {session.session_date:%a %d %b}: probably {topics_txt}",
        body=result.summary_md, data={"session_id": session.id, "course_id": course.id,
                                      "likely_topics": result.likely_topics, "cited_section_ids": cited},
        actions=[cards.action("dismiss", "Got it", primary=True)], course_id=course.id,
        dedupe_key=f"catch_up_ready:{session.id}:{ctx.job_id}")
    trace.finish("succeeded", f"likely covered: {topics_txt}")
    ctx.db.commit()
    return {"card_id": card.id, "likely_topics": result.likely_topics}


# ------------------------------------------------------------------ questions from the command bar
async def handle_answer_question(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    course = ctx.db.get(Course, payload["course_id"]) if payload.get("course_id") else None
    ctx.state.update(course_id=course.id if course else None)
    scope = f"Course: {course.name}." if course else "Any of the student's courses."
    dates = ""
    if payload.get("since") or payload.get("until"):
        dates = f" Date range: {payload.get('since') or '…'} to {payload.get('until') or '…'}."
    res = await QAAgent().run(ctx, f"QUESTION: {question}\n{scope}{dates} Today is {ctx.now.date().isoformat()}.")
    if res.finished_by != "answer" or not isinstance(res.terminal_result, dict):
        raise JobFailed(f"The Q&A agent ended with state {res.state} without an answer")
    ans = res.terminal_result
    citations: dict[str, dict[str, str]] = {}
    for sid in ans.get("cited_section_ids", []):
        sec = ctx.db.get(NoteSection, sid)
        topic = ctx.db.get(Topic, sec.topic_id) if sec else None
        if sec and topic:
            citations[sid] = {"topic_id": topic.id, "topic_title": topic.title, "heading": sec.heading,
                              "course_id": sec.course_id}
    card = cards.create_card(
        ctx.db, "answer", question[:200], body=ans["answer_md"],
        data={"question": question, "citations": citations, "cited_session_ids": ans.get("cited_session_ids", []),
              "run_id": res.run_id}, course_id=course.id if course else None,
        actions=[cards.action("dismiss", "Got it", primary=True)])
    ctx.db.commit()
    return {"card_id": card.id, "run_id": res.run_id}


HANDLERS = {
    "catch_up": handle_catch_up,
    "answer_question": handle_answer_question,
    "class_ended": handle_class_ended,
    "check_missed_upload": handle_check_missed,
    "missed_upload": handle_missed_upload,
    "process_upload": handle_process_upload,
    "build_exam_pack": handle_build_exam_pack,
}
