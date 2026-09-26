"""The Novi feed (UX.md §3): cards, live runs, what happened since the last visit, what's next, command bar."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.describe import AGENT_NAMES, describe_run, describe_step, headline
from app.api.deps import DB, CurrentUser, get_or_404
from app.api.schemas import JobOut
from app.command.service import CommandResult, run_command
from app.config.brand import get_brand
from app.config.settings import REPO_ROOT
from app.db.base import utcnow
from app.db.engine import system_session_ctx
from app.db.models import (
    AgentAction,
    AgentRun,
    AgentStep,
    Assignment,
    ClassSession,
    ClassSlot,
    Course,
    Exam,
    Job,
    Notification,
    TriggerLog,
    User,
)
from app.llm.client import get_llm
from app.orchestrator import actions, cards
from app.orchestrator.events import emit
from app.orchestrator.state_machines import JOB, transition
from app.orchestrator.timeutil import local_dt, local_today

router = APIRouter(tags=["feed"])
public = APIRouter(tags=["meta"])


# ------------------------------------------------------------------ schemas
class CardOut(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    link: str
    data: dict[str, Any]
    actions: list[dict[str, Any]]
    status: str
    priority: int
    action_id: str | None
    undoable: bool = False
    course_id: str | None
    created_at: datetime


class StepOut(BaseModel):
    idx: int
    kind: str
    name: str
    label: str
    ok: bool
    latency_ms: int
    created_at: datetime


class RunOut(BaseModel):
    id: str
    agent: str
    agent_name: str
    mode: str
    state: str
    summary: str
    headline: str
    goal: str
    output: str
    cost_usd: float
    llm_calls: int
    created_at: datetime
    finished_at: datetime | None
    steps: list[StepOut] = []
    undo_action_id: str | None = None


class NextItem(BaseModel):
    at: datetime
    kind: Literal["class_end", "check", "exam_pack"]
    text: str


class WeekItem(BaseModel):
    course_id: str
    course: str
    color: str
    start: str
    end: str
    state: str  # upcoming | in_progress | ended | notes_in | missed


class FeedOut(BaseModel):
    user_name: str
    is_guest: bool
    status_line: str
    counts: dict[str, int]
    cards: list[CardOut]
    live: list[RunOut]
    since: list[RunOut]
    next: list[NextItem]
    week: list[WeekItem]
    policy: list[dict[str, str]]
    suggestions: list[str]


class ActIn(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    value: str | None = Field(default=None, max_length=20000)


class ActOut(BaseModel):
    message: str
    card: CardOut | None = None
    job: JobOut | None = None


class CommandIn(BaseModel):
    text: str = Field(min_length=2, max_length=500)


# ------------------------------------------------------------------ helpers
def card_out(db: DB, c: Notification) -> CardOut:
    undoable = False
    if c.action_id:
        act = db.get(AgentAction, c.action_id)
        undoable = bool(act and act.status == "applied" and utcnow() - act.created_at <= actions.UNDO_WINDOW)
    acts = [a for a in c.actions if a.get("id") != "undo" or undoable]
    return CardOut(id=c.id, kind=c.kind, title=c.title, body=c.body, link=c.link, data=c.data, actions=acts,
                   status=c.status, priority=c.priority, action_id=c.action_id, undoable=undoable,
                   course_id=c.course_id, created_at=c.created_at)


def run_out(db: DB, r: AgentRun, with_steps: bool = True, max_steps: int = 40) -> RunOut:
    steps: list[StepOut] = []
    if with_steps:
        rows = list(db.scalars(select(AgentStep).where(AgentStep.run_id == r.id).order_by(AgentStep.idx.desc())
                               .limit(max_steps)))
        steps = [StepOut(idx=s.idx, kind=s.kind, name=s.name, label=describe_step(s.kind, s.name, s.input, s.output, s.ok),
                         ok=s.ok, latency_ms=s.latency_ms, created_at=s.created_at) for s in reversed(rows)]
    undo_id = None
    if r.job_id:
        act = db.scalar(select(AgentAction).where(AgentAction.job_id == r.job_id, AgentAction.status == "applied"))
        undo_id = act.id if act else None
    return RunOut(id=r.id, agent=r.agent, agent_name=AGENT_NAMES.get(r.agent, r.agent), mode=r.mode, state=r.state,
                  summary=describe_run(r.agent, r.goal, r.output, r.state),
                  headline=headline(r.agent, r.output, r.state), goal=r.goal[:500], output=r.output[:500],
                  cost_usd=r.cost_usd, llm_calls=r.llm_calls, created_at=r.created_at, finished_at=r.finished_at,
                  steps=steps, undo_action_id=undo_id)


def _user_row(user_id: str) -> User:
    with system_session_ctx() as sdb:
        u = sdb.get(User, user_id)
        assert u is not None
        return u


def _next_items(db: DB, user: User, now: datetime) -> list[NextItem]:
    items: list[NextItem] = []
    tz = user.timezone
    today = local_today(now, tz)
    courses = {c.id: c for c in db.scalars(select(Course))}
    for slot in db.scalars(select(ClassSlot)):
        for add in range(0, 8):
            d = today + timedelta(days=add)
            if d.weekday() != slot.weekday or (user.semester_start and d < user.semester_start) or \
                    (user.semester_end and d > user.semester_end):
                continue
            ends = local_dt(d, slot.end_time, tz)
            if ends > now:
                items.append(NextItem(at=ends, kind="class_end",
                                      text=f"I'll ask for your {courses[slot.course_id].name} notes when class ends"))
                break
    for job in db.scalars(select(Job).where(Job.state == "queued", Job.run_after > now, Job.type == "check_missed_upload")):
        s = db.get(ClassSession, job.payload.get("session_id"))
        if s is not None and s.course_id in courses:
            items.append(NextItem(at=job.run_after, kind="check",
                                  text=f"I'll check whether your {courses[s.course_id].name} notes arrived"))
    fired = {k for (k,) in db.execute(select(TriggerLog.key)).all()}
    for exam in db.scalars(select(Exam)):
        days = (exam.exam_date - today).days
        for t in (14, 7, 3):
            if days > t and f"exam_approaching:{exam.id}:T-{t}" not in fired:
                when = local_dt(exam.exam_date - timedelta(days=t), "08:00", tz)
                items.append(NextItem(at=when, kind="exam_pack",
                                      text=f"I'll {'build' if t == 14 else 'refresh'} your {exam.title} Exam Pack (T-{t})"))
                break
    items.sort(key=lambda i: i.at)
    class_ends = [i for i in items if i.kind == "class_end"][:2]  # the next two are enough; the rest is the week
    return [i for i in items if i.kind != "class_end" or i in class_ends][:5]


def _week(db: DB, user: User, now: datetime) -> list[WeekItem]:
    tz = user.timezone
    today = local_today(now, tz)
    courses = {c.id: c for c in db.scalars(select(Course))}
    sessions = {s.slot_id: s for s in db.scalars(select(ClassSession).where(ClassSession.session_date == today))}
    out = []
    for slot in db.scalars(select(ClassSlot).where(ClassSlot.weekday == today.weekday()).order_by(ClassSlot.start_time)):
        start, end = local_dt(today, slot.start_time, tz), local_dt(today, slot.end_time, tz)
        s = sessions.get(slot.id)
        state = "upcoming" if now < start else "in_progress" if now < end else "ended"
        if s is not None and s.state in ("uploaded", "processed"):
            state = "notes_in"
        elif s is not None and s.state == "missed":
            state = "missed"
        c = courses[slot.course_id]
        out.append(WeekItem(course_id=c.id, course=c.name, color=c.color, start=slot.start_time, end=slot.end_time,
                            state=state))
    return out


def _status_line(counts: dict[str, int], next_items: list[NextItem], tz: str) -> str:
    """One honest sentence, derived from counts and the next planned item."""
    n = counts["needs_you"]
    if counts["running"]:
        head = "I'm working on something right now — watch it below."
    elif n:
        head = f"{n} thing{'s need' if n != 1 else ' needs'} you. Everything else is handled."
    else:
        head = "All caught up."
    if next_items:
        when = next_items[0].at.astimezone(ZoneInfo(tz)).strftime("%a %H:%M")
        return f"{head} Next: {next_items[0].text} ({when})."
    if not counts["classes"]:
        return f"{head} Add your timetable and I'll start following your classes."
    return head


def features() -> dict[str, bool]:
    return json.loads((REPO_ROOT / "config" / "features.json").read_text())


# ------------------------------------------------------------------ endpoints
@public.get("/meta")
def meta() -> dict[str, Any]:
    """Brand + feature flags (public: no user data)."""
    b = get_brand()
    return {"brand": {"name": b.name, "tagline": b.tagline, "slug": b.slug}, "features": features()}


@router.get("/feed", response_model=FeedOut)
def feed(user: CurrentUser, db: DB) -> FeedOut:
    now = utcnow()
    row = _user_row(user.id)
    open_cards = list(db.scalars(select(Notification).where(Notification.status == "open")
                                 .order_by(Notification.priority.desc(), Notification.created_at.desc()).limit(30)))
    running = list(db.scalars(select(AgentRun).where(AgentRun.state == "running").order_by(AgentRun.created_at.desc())
                              .limit(5)))
    since_q = select(AgentRun).where(AgentRun.state != "running").order_by(AgentRun.created_at.desc()).limit(10)
    if row.last_seen_at:
        since_q = since_q.where(AgentRun.finished_at >= row.last_seen_at - timedelta(hours=1))
    since = [r for r in db.scalars(since_q) if not (r.agent == "planner" and "tick" in r.goal.lower() and not r.output)]
    next_items = _next_items(db, row, now)
    week = _week(db, row, now)
    counts = {"needs_you": len(open_cards), "running": len(running),
              "classes": len(list(db.scalars(select(ClassSlot.id))))}
    exams = list(db.scalars(select(Exam).order_by(Exam.exam_date).limit(2)))
    courses = list(db.scalars(select(Course).order_by(Course.created_at).limit(3)))
    suggestions = [f"Make me a 1h exam on {courses[0].name}" if courses else "",
                   f"What did we cover last week in {courses[-1].name}?" if courses else "",
                   f"Move my {exams[0].title} to {(exams[0].exam_date + timedelta(days=7)):%d %b}" if exams else ""]
    return FeedOut(
        user_name=row.display_name or ("there" if row.is_guest else row.email.split("@")[0]), is_guest=row.is_guest,
        status_line=_status_line(counts, next_items, row.timezone), counts=counts,
        cards=[card_out(db, c) for c in open_cards], live=[run_out(db, r) for r in running],
        since=[run_out(db, r, with_steps=False) for r in since], next=next_items, week=week,
        policy=actions.AUTONOMY_POLICY, suggestions=[s for s in suggestions if s])


@router.post("/feed/seen", status_code=204)
def feed_seen(user: CurrentUser) -> None:
    with system_session_ctx() as sdb:
        row = sdb.get(User, user.id)
        assert row is not None
        row.last_seen_at = utcnow()


@router.get("/runs/live", response_model=list[RunOut])
def live_runs(db: DB, job_id: str | None = None) -> list[RunOut]:
    """Running runs + runs finished in the last 10 minutes (or the runs of one job), with labelled steps."""
    q = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(8)
    if job_id:
        q = q.where(AgentRun.job_id == job_id)
    else:
        cutoff = utcnow() - timedelta(minutes=10)
        q = q.where((AgentRun.state == "running") | (AgentRun.finished_at >= cutoff))
    return [run_out(db, r) for r in db.scalars(q)
            if job_id or not (r.agent == "planner" and "tick" in r.goal.lower() and not r.output)]


@router.get("/runs/{run_id}", response_model=RunOut)
def run_detail(run_id: str, db: DB) -> RunOut:
    return run_out(db, get_or_404(db, AgentRun, run_id), max_steps=200)


@router.get("/cards", response_model=list[CardOut])
def list_cards(db: DB, status: str = "open", limit: int = 50) -> list[CardOut]:
    q = select(Notification).order_by(Notification.created_at.desc()).limit(min(limit, 200))
    if status != "all":
        q = q.where(Notification.status == status)
    return [card_out(db, c) for c in db.scalars(q)]


@router.post("/cards/{card_id}/act", response_model=ActOut)
async def act(card_id: str, body: ActIn, user: CurrentUser, db: DB) -> ActOut:
    card = get_or_404(db, Notification, card_id)
    if card.status != "open":
        raise HTTPException(409, f"This card is already {card.status}.")
    allowed = {a["id"] for a in card.actions} | {"dismiss"}
    if body.action not in allowed:
        raise HTTPException(422, f"'{body.action}' is not an action of this card")
    job: Job | None = None
    try:
        if body.action == "dismiss":
            cards.resolve(card, "dismissed")
            msg = "Dismissed."
        elif body.action in ("undo", "approve", "reject"):
            action_row = get_or_404(db, AgentAction, card.action_id or "")
            if body.action == "undo":
                msg = await actions.undo(db, user.id, action_row)
            elif body.action == "approve":
                msg = actions.approve(db, action_row)
            else:
                msg = actions.reject(db, action_row)
            cards.resolve(card)
        elif body.action == "set_exam_date":
            course = get_or_404(db, Course, card.data.get("course_id", ""))
            try:
                d = date.fromisoformat(body.value or "")
            except ValueError as exc:
                raise HTTPException(422, "value must be a date (YYYY-MM-DD)") from exc
            exam = cards.create_exam_with_followups(db, course, d)
            cards.resolve(card)
            msg = f"Saved: {exam.title} on {d:%d %b}. I'll build your Exam Pack 14 days before."
        elif body.action == "save_syllabus":
            course = get_or_404(db, Course, card.data.get("course_id", ""))
            if not (body.value or "").strip():
                raise HTTPException(422, "paste the syllabus text")
            course.syllabus = body.value.strip()[:20000]  # type: ignore[union-attr]
            cards.resolve(card)
            msg = f"Saved the {course.name} syllabus. I'll use it to track the pace."
        elif body.action == "catch_up":
            job = emit(db, "catch_up_requested", {"session_id": card.data.get("session_id")}, source="manual")
            cards.resolve(card)
            msg = "On it — preparing a catch-up from your notes and the syllabus."
        elif body.action == "connect_calendar":
            from app.api.routers.integrations import connect_calendar

            out = await connect_calendar(db, user.id, body.value or "")
            job, msg = db.get(Job, out.job.id), out.message
            cards.resolve(card)
        elif body.action == "fetch_guide":
            from app.api.routers.integrations import apply_guide

            course = get_or_404(db, Course, card.data.get("course_id", ""))
            msg = (await apply_guide(db, course, body.value or "")).message
            cards.resolve(card)
        elif body.action == "mark_done":
            a = get_or_404(db, Assignment, card.data.get("assignment_id", ""))
            a.done = True
            cards.resolve(card)
            msg = f"Marked “{a.title}” as done."
        elif body.action == "retry":
            job = get_or_404(db, Job, card.data.get("job_id", ""))
            if job.state == "failed":
                transition(JOB, job, "queued")
                job.error, job.run_after = "", utcnow()
            cards.resolve(card)
            msg = "Retrying…"
        else:
            raise HTTPException(422, f"'{body.action}' is handled by the app (link / upload), not by the server")
    except actions.UndoRefused as exc:
        raise HTTPException(409, str(exc)) from exc
    db.flush()
    return ActOut(message=msg, card=card_out(db, card), job=JobOut.model_validate(job) if job else None)


@router.post("/command", response_model=CommandResult)
async def command(body: CommandIn, user: CurrentUser, db: DB) -> CommandResult:
    row = _user_row(user.id)
    now = utcnow()
    return await run_command(db, get_llm(), user.id, body.text, local_today(now, row.timezone), now)


class ActionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    kind: str
    risk: str
    status: str
    title: str
    job_id: str | None
    created_at: datetime
    resolved_at: datetime | None


@router.get("/actions", response_model=list[ActionOut])
def list_actions(db: DB, limit: int = 50) -> list[AgentAction]:
    """Everything Novi did or proposed, newest first (applied, proposed, rejected, undone)."""
    return list(db.scalars(select(AgentAction).order_by(AgentAction.created_at.desc()).limit(min(limit, 200))))


@router.post("/actions/{action_id}/undo", response_model=ActOut)
async def undo_action(action_id: str, user: CurrentUser, db: DB) -> ActOut:
    act_row = get_or_404(db, AgentAction, action_id)
    try:
        msg = await actions.undo(db, user.id, act_row)
    except actions.UndoRefused as exc:
        raise HTTPException(409, str(exc)) from exc
    return ActOut(message=msg)
