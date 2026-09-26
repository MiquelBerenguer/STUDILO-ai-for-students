"""Course Memory agent tools."""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.base import Tool, ToolContext, ToolError
from app.db.models import ClassSession, Course, CourseMemory, OpenQuestion, Topic, TopicDependency
from app.orchestrator.state_machines import CLASS_SESSION, transition
from app.tools import store


def _course(ctx: ToolContext) -> str:
    return ctx.state["course_id"]


def _session(ctx: ToolContext, sid: str) -> ClassSession:
    s = store.must_get(ctx.db, ClassSession, sid, "session")
    if s.course_id != _course(ctx):
        raise ToolError("session belongs to another subject")
    return s


def _topic(ctx: ToolContext, tid: str) -> Topic:
    t = store.must_get(ctx.db, Topic, tid, "topic")
    if t.course_id != _course(ctx):
        raise ToolError("topic belongs to another subject")
    return t


def memory_row(ctx_db, course_id: str) -> CourseMemory:  # type: ignore[no-untyped-def]
    mem = ctx_db.scalar(select(CourseMemory).where(CourseMemory.course_id == course_id))
    if mem is None:
        mem = CourseMemory(course_id=course_id)
        ctx_db.add(mem)
        ctx_db.flush()
    return mem


def computed_pace(db, course_id: str, today) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Deterministic pace stats over the last 4 weeks (no LLM)."""
    since = today - timedelta(days=28)
    sessions = list(db.scalars(select(ClassSession).where(ClassSession.course_id == course_id,
                                                         ClassSession.session_date >= since)))
    topics = list(db.scalars(select(Topic).where(Topic.course_id == course_id)))
    new_topics = [t for t in topics if t.created_at.date() >= since]
    return {
        "window_days": 28,
        "sessions": len(sessions),
        "missed": sum(1 for s in sessions if s.state == "missed"),
        "with_notes": sum(1 for s in sessions if s.state in ("uploaded", "processed")),
        "new_topics": len(new_topics),
        "topics_per_week": round(len(new_topics) / 4, 2),
        "total_topics": len(topics),
    }


class GetSessionsArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=40)


class AppendSummaryArgs(BaseModel):
    session_id: str
    summary_md: str = Field(min_length=1, max_length=4000)
    topic_ids: list[str] = Field(default_factory=list)


class PaceArgs(BaseModel):
    topics_per_week: float = Field(ge=0, le=50)
    syllabus_position: str = Field(max_length=1000, description="where the class is against the syllabus")
    pace_note: str = Field(default="", max_length=1000)


class FlagArgs(BaseModel):
    session_id: str
    reason: str = Field(max_length=200)


class QuestionArgs(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    topic_id: str | None = None


class LinkTopicsArgs(BaseModel):
    topic_id: str = Field(description="the topic that builds on another")
    depends_on_topic_id: str


class FinishArgs(BaseModel):
    summary: str = Field(max_length=2000)


def get_sessions_tool(ctx: ToolContext, a: GetSessionsArgs) -> dict[str, object]:
    course = store.must_get(ctx.db, Course, _course(ctx), "course")
    rows = list(ctx.db.scalars(select(ClassSession).where(ClassSession.course_id == course.id)
                               .order_by(ClassSession.session_date.desc()).limit(a.limit)))
    topics = {t.id: t.title for t in ctx.db.scalars(select(Topic).where(Topic.course_id == course.id))}
    mem = memory_row(ctx.db, course.id)
    open_q = list(ctx.db.scalars(select(OpenQuestion).where(OpenQuestion.course_id == course.id,
                                                            OpenQuestion.status == "open")))
    return {
        "course": course.name, "syllabus": course.syllabus[:3000],
        "memory": {"topics_per_week": mem.topics_per_week, "syllabus_position": mem.syllabus_position,
                   "pace_note": mem.pace_note},
        "computed_pace": computed_pace(ctx.db, course.id, ctx.now.date()),
        "topics": [{"topic_id": k, "title": v} for k, v in topics.items()],
        "open_questions": [q.text for q in open_q],
        "sessions": [{"session_id": s.id, "date": s.session_date.isoformat(), "state": s.state,
                      "summary": s.summary_md[:800], "topics": [topics.get(t, t) for t in s.topic_ids]} for s in rows],
    }


def append_session_summary_tool(ctx: ToolContext, a: AppendSummaryArgs) -> dict[str, object]:
    s = _session(ctx, a.session_id)
    for tid in a.topic_ids:
        _topic(ctx, tid)
    s.summary_md = (s.summary_md + "\n\n" + a.summary_md.strip()).strip()
    s.topic_ids = sorted(set(s.topic_ids) | set(a.topic_ids))
    ctx.state["summarised"] = True
    return {"ok": True}


def update_course_pace_tool(ctx: ToolContext, a: PaceArgs) -> dict[str, object]:
    mem = memory_row(ctx.db, _course(ctx))
    mem.topics_per_week, mem.syllabus_position, mem.pace_note = a.topics_per_week, a.syllabus_position, a.pace_note
    return {"ok": True}


def flag_missed_session_tool(ctx: ToolContext, a: FlagArgs) -> dict[str, object]:
    s = _session(ctx, a.session_id)
    if s.state == "missed":
        return {"ok": True, "note": "already flagged"}
    if not CLASS_SESSION.can(s.state, "missed"):
        raise ToolError(f"session is {s.state}; only sessions awaiting upload can be flagged as missed")
    transition(CLASS_SESSION, s, "missed")
    s.missed_reason = a.reason
    return {"ok": True}


def add_open_question_tool(ctx: ToolContext, a: QuestionArgs) -> dict[str, object]:
    if a.topic_id:
        _topic(ctx, a.topic_id)
    dup = ctx.db.scalar(select(OpenQuestion).where(OpenQuestion.course_id == _course(ctx),
                                                   OpenQuestion.text == a.text.strip()))
    if dup:
        return {"question_id": dup.id, "note": "already recorded"}
    q = OpenQuestion(course_id=_course(ctx), topic_id=a.topic_id, text=a.text.strip(),
                     source_upload_id=ctx.state.get("upload_id"))
    ctx.db.add(q)
    ctx.db.flush()
    return {"question_id": q.id}


def link_topics_tool(ctx: ToolContext, a: LinkTopicsArgs) -> dict[str, object]:
    if a.topic_id == a.depends_on_topic_id:
        raise ToolError("a topic cannot depend on itself")
    _topic(ctx, a.topic_id)
    _topic(ctx, a.depends_on_topic_id)
    exists = ctx.db.scalar(select(TopicDependency).where(TopicDependency.topic_id == a.topic_id,
                                                         TopicDependency.depends_on_id == a.depends_on_topic_id))
    if not exists:
        dep = TopicDependency(course_id=_course(ctx), topic_id=a.topic_id, depends_on_id=a.depends_on_topic_id)
        ctx.db.add(dep)
        ctx.db.flush()
        store.fx(ctx.state)["created_dependencies"].append(dep.id)
    return {"ok": True}


def finish_tool(ctx: ToolContext, a: FinishArgs) -> dict[str, object]:
    if ctx.state.get("require_summary") and not ctx.state.get("summarised"):
        raise ToolError("append the session summary before finishing")
    return {"summary": a.summary}


def memory_tools() -> list[Tool]:
    return [
        Tool("get_sessions", "Recent class sessions, computed pace, topics, open questions and syllabus.",
             GetSessionsArgs, get_sessions_tool),
        Tool("append_session_summary", "Append what was covered to a session's summary.", AppendSummaryArgs,
             append_session_summary_tool),
        Tool("update_course_pace", "Record the course pace and where the class is against the syllabus.", PaceArgs,
             update_course_pace_tool),
        Tool("flag_missed_session", "Flag a class that passed without notes.", FlagArgs, flag_missed_session_tool),
        Tool("add_open_question", "Record an open doubt / unresolved question from the notes.", QuestionArgs,
             add_open_question_tool),
        Tool("link_topics", "Record that one topic builds on another.", LinkTopicsArgs, link_topics_tool),
        Tool("finish", "Finish the memory update.", FinishArgs, finish_tool, terminal=True),
    ]
