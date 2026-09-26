"""Q&A agent tools: answer questions from the student's own notes and class history."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.base import Tool, ToolContext, ToolError
from app.db.models import ClassSession, Course, NoteSection, Topic
from app.tools import store


class QSearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=6, ge=1, le=10)


class SessionsArgs(BaseModel):
    since: date | None = None
    until: date | None = None
    limit: int = Field(default=15, ge=1, le=40)


class ReadArgs(BaseModel):
    section_ids: list[str] = Field(min_length=1, max_length=10)


class AnswerArgs(BaseModel):
    answer_md: str = Field(min_length=1, max_length=6000)
    cited_section_ids: list[str] = Field(default_factory=list, max_length=12)
    cited_session_ids: list[str] = Field(default_factory=list, max_length=12)


def _course_filter(ctx: ToolContext) -> str | None:
    return ctx.state.get("course_id")


async def search_tool(ctx: ToolContext, a: QSearchArgs) -> list[dict[str, object]]:
    ctx.db.commit()
    return await store.search_notes(ctx.db, ctx.user_id, a.query, course_id=_course_filter(ctx), k=a.k)


def sessions_tool(ctx: ToolContext, a: SessionsArgs) -> list[dict[str, object]]:
    q = select(ClassSession).order_by(ClassSession.session_date.desc()).limit(a.limit)
    if _course_filter(ctx):
        q = q.where(ClassSession.course_id == _course_filter(ctx))
    if a.since:
        q = q.where(ClassSession.session_date >= a.since)
    if a.until:
        q = q.where(ClassSession.session_date <= a.until)
    courses = {c.id: c.name for c in ctx.db.scalars(select(Course))}
    topics = {t.id: t.title for t in ctx.db.scalars(select(Topic))}
    return [{"session_id": s.id, "course": courses.get(s.course_id), "date": s.session_date.isoformat(),
             "state": s.state, "summary": s.summary_md[:1200], "topics": [topics.get(t, t) for t in s.topic_ids]}
            for s in ctx.db.scalars(q)]


def read_tool(ctx: ToolContext, a: ReadArgs) -> list[dict[str, object]]:
    out = []
    for sid in a.section_ids:
        s = ctx.db.get(NoteSection, sid)
        if s is None:
            raise ToolError(f"section {sid!r} not found")
        out.append({"section_id": s.id, "heading": s.heading, "content_md": s.content_md[:4000]})
    return out


def answer_tool(ctx: ToolContext, a: AnswerArgs) -> dict[str, object]:
    for sid in a.cited_section_ids:
        if ctx.db.get(NoteSection, sid) is None:
            raise ToolError(f"cited section {sid!r} is not one of the student's note sections")
    for sid in a.cited_session_ids:
        if ctx.db.get(ClassSession, sid) is None:
            raise ToolError(f"cited session {sid!r} does not exist")
    return a.model_dump()


def qa_tools() -> list[Tool]:
    return [
        Tool("search_notes", "Semantic search over the student's notes (limited to one course if given).",
             QSearchArgs, search_tool),
        Tool("get_course_sessions", "Class history: what was covered in each class, filtered by date range.",
             SessionsArgs, sessions_tool),
        Tool("read_sections", "Read note sections by id.", ReadArgs, read_tool),
        Tool("answer", "Give the final answer with citations.", AnswerArgs, answer_tool, terminal=True),
    ]
