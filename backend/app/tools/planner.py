"""Planner/Scheduler agent tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.base import Tool, ToolContext
from app.db.base import utcnow
from app.db.engine import system_session_ctx
from app.db.models import ClassSession, ClassSlot, Course, Exam, Job, OpenQuestion, User
from app.orchestrator import cards
from app.tools import store
from app.tools.memory import computed_pace, memory_row

JobType = Literal["check_missed_upload"]


class NoArgs(BaseModel):
    pass


class CourseArg(BaseModel):
    course_id: str


class ReminderArgs(BaseModel):
    kind: Literal["upload_prompt", "missed_class", "info"]
    title: str = Field(max_length=200)
    body: str = Field(default="", max_length=2000)
    link: str = Field(default="", max_length=300)
    data: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list, description="typed card actions (cards.action)")
    dedupe_key: str | None = Field(default=None, max_length=200)


class ScheduleArgs(BaseModel):
    type: JobType
    payload: dict[str, Any] = Field(default_factory=dict)
    run_after: datetime


def get_schedule_tool(ctx: ToolContext, _a: NoArgs) -> dict[str, object]:
    with system_session_ctx() as sdb:  # identity row: only our own user id is read
        user = sdb.get(User, ctx.user_id)
        assert user is not None
        profile = {"timezone": user.timezone, "semester_start": user.semester_start,
                   "semester_end": user.semester_end, "missed_after_hours": user.missed_after_hours}
    courses = {c.id: c.name for c in ctx.db.scalars(select(Course))}
    slots = list(ctx.db.scalars(select(ClassSlot).order_by(ClassSlot.weekday, ClassSlot.start_time)))
    return {**profile, "slots": [{"slot_id": s.id, "course_id": s.course_id, "course": courses.get(s.course_id),
                                  "weekday": s.weekday, "start": s.start_time, "end": s.end_time} for s in slots]}


def get_exam_dates_tool(ctx: ToolContext, _a: NoArgs) -> list[dict[str, object]]:
    return [{"exam_id": e.id, "course_id": e.course_id, "title": e.title, "date": e.exam_date.isoformat(),
             "days_left": (e.exam_date - ctx.now.date()).days}
            for e in ctx.db.scalars(select(Exam).order_by(Exam.exam_date))]


def get_course_memory_tool(ctx: ToolContext, a: CourseArg) -> dict[str, object]:
    course = store.must_get(ctx.db, Course, a.course_id, "course")
    mem = memory_row(ctx.db, course.id)
    missed = list(ctx.db.scalars(select(ClassSession).where(ClassSession.course_id == course.id,
                                                           ClassSession.state == "missed")))
    open_q = ctx.db.scalars(select(OpenQuestion).where(OpenQuestion.course_id == course.id,
                                                       OpenQuestion.status == "open")).all()
    return {"course": course.name, "syllabus_position": mem.syllabus_position, "topics_per_week": mem.topics_per_week,
            "computed_pace": computed_pace(ctx.db, course.id, ctx.now.date()),
            "missed_sessions": [s.session_date.isoformat() for s in missed], "open_questions": len(open_q)}


def create_reminder_tool(ctx: ToolContext, a: ReminderArgs) -> dict[str, object]:
    """Puts an action card in the student's Novi feed (and inbox bell)."""
    card = cards.create_card(ctx.db, a.kind, a.title, body=a.body, link=a.link, data=a.data,
                             actions=a.actions or None, dedupe_key=a.dedupe_key,
                             course_id=a.data.get("course_id"))
    return {"card_id": card.id}


def schedule_job_tool(ctx: ToolContext, a: ScheduleArgs) -> dict[str, object]:
    run_after = a.run_after if a.run_after.tzinfo else a.run_after.replace(tzinfo=utcnow().tzinfo)
    job = Job(type=a.type, payload=a.payload, run_after=run_after)
    ctx.db.add(job)
    ctx.db.flush()
    return {"job_id": job.id, "run_after": run_after.isoformat()}


PLANNER_TOOLS = {t.name: t for t in [
    Tool("get_schedule", "Weekly class slots, timezone and semester dates.", NoArgs, get_schedule_tool),
    Tool("get_exam_dates", "Exams with days left.", NoArgs, get_exam_dates_tool),
    Tool("get_course_memory", "Pace, missed sessions and open questions of one course.", CourseArg,
         get_course_memory_tool),
    Tool("create_reminder", "Put an action card in the student's Novi feed.", ReminderArgs, create_reminder_tool),
    Tool("schedule_job", "Schedule a follow-up job at a given time.", ScheduleArgs, schedule_job_tool),
]}
