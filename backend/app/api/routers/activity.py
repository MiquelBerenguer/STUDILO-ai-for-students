"""Jobs, events/triggers, inbox and the activity/cost views."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_or_404
from app.api.schemas import AgentRunOut, AgentStepOut, EventIn, JobOut, LLMCallOut, NotificationOut, TickIn
from app.db.base import utcnow
from app.db.models import (
    AgentRun,
    AgentStep,
    ClassSession,
    ClassSlot,
    Event,
    Exam,
    IngestionLog,
    Job,
    LLMCall,
    Notification,
)
from app.orchestrator import worker
from app.orchestrator.events import emit
from app.orchestrator.state_machines import JOB, transition

router = APIRouter(tags=["activity"])


# ------------------------------------------------------------------ jobs
@router.get("/jobs", response_model=list[JobOut])
def list_jobs(db: DB, limit: int = 30, state: str | None = None) -> list[Job]:
    q = select(Job).order_by(Job.created_at.desc()).limit(min(limit, 200))
    if state:
        q = q.where(Job.state == state)
    return list(db.scalars(q))


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: DB) -> Job:
    return get_or_404(db, Job, job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: str, db: DB) -> Job:
    job = get_or_404(db, Job, job_id)
    if job.state != "failed":
        raise HTTPException(409, "Only failed jobs can be retried")
    transition(JOB, job, "queued")
    job.error, job.run_after = "", utcnow()
    return job


# ------------------------------------------------------------------ events (manual triggers)
@router.post("/events", response_model=JobOut, status_code=202)
def post_event(body: EventIn, user: CurrentUser, db: DB) -> Job:
    """UI actions emit exactly the events the scheduler emits."""
    if body.type == "class_ended":
        slot = get_or_404(db, ClassSlot, body.slot_id or "")
        d = body.session_date or date.today()
        return emit(db, "class_ended", {"slot_id": slot.id, "session_date": d.isoformat()}, source="manual")
    if body.type == "class_slot_passed_without_upload":
        sessions = list(db.scalars(select(ClassSession).where(ClassSession.state == "awaiting_upload")
                                   .order_by(ClassSession.session_date)))
        if body.slot_id:
            sessions = [s for s in sessions if s.slot_id == body.slot_id]
        if not sessions:
            raise HTTPException(409, "No class is waiting for notes right now")
        return emit(db, "class_slot_passed_without_upload", {"session_id": sessions[0].id}, source="manual")
    if body.type == "exam_approaching":
        exam = get_or_404(db, Exam, body.exam_id or "")
        return emit(db, "exam_approaching", {"exam_id": exam.id}, source="manual")
    if not body.course_id:
        raise HTTPException(422, "course_id is required")
    return emit(db, "exam_requested", {"course_id": body.course_id}, source="manual")


class TickOut(BaseModel):
    now: datetime
    actions: list[str]


@router.post("/simulate/tick", response_model=TickOut)
async def simulate_tick(body: TickIn, user: CurrentUser) -> TickOut:
    """Run the Planner now, or at a simulated time, for the signed-in user only."""
    now = body.now or utcnow()
    if now.tzinfo is None:
        raise HTTPException(422, "now must include a timezone offset")
    out = await worker.tick(now=now, user_id=user.id)
    return TickOut(now=now, actions=out.get(user.id, []))


# ------------------------------------------------------------------ inbox
@router.get("/inbox", response_model=list[NotificationOut])
def inbox(db: DB, unread: bool = False, limit: int = 50) -> list[Notification]:
    q = select(Notification).order_by(Notification.created_at.desc()).limit(min(limit, 200))
    if unread:
        q = q.where(Notification.read_at.is_(None))
    return list(db.scalars(q))


@router.post("/inbox/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: str, db: DB) -> Notification:
    n = get_or_404(db, Notification, notification_id)
    n.read_at = n.read_at or utcnow()
    return n


@router.post("/inbox/read-all", status_code=204)
def mark_all_read(db: DB) -> None:
    for n in db.scalars(select(Notification).where(Notification.read_at.is_(None))):
        n.read_at = utcnow()


# ------------------------------------------------------------------ activity & costs
@router.get("/activity/runs", response_model=list[AgentRunOut])
def runs(db: DB, limit: int = 50, agent: str | None = None) -> list[AgentRun]:
    q = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(min(limit, 300))
    if agent:
        q = q.where(AgentRun.agent == agent)
    return list(db.scalars(q))


class RunDetailOut(BaseModel):
    run: AgentRunOut
    steps: list[AgentStepOut]
    llm_calls: list[LLMCallOut]


@router.get("/activity/runs/{run_id}", response_model=RunDetailOut)
def run_detail(run_id: str, db: DB) -> RunDetailOut:
    run = get_or_404(db, AgentRun, run_id)
    steps = db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.idx))
    calls = db.scalars(select(LLMCall).where(LLMCall.agent_run_id == run.id).order_by(LLMCall.created_at))
    return RunDetailOut(run=AgentRunOut.model_validate(run), steps=[AgentStepOut.model_validate(s) for s in steps],
                        llm_calls=[LLMCallOut.model_validate(c) for c in calls])


@router.get("/activity/llm-calls", response_model=list[LLMCallOut])
def llm_calls(db: DB, limit: int = 100) -> list[LLMCall]:
    return list(db.scalars(select(LLMCall).order_by(LLMCall.created_at.desc()).limit(min(limit, 500))))


class SummaryOut(BaseModel):
    total_cost_usd: float
    llm_calls: int
    llm_failed_calls: int
    unpriced_calls: int
    deterministic_steps: int
    tool_steps: int
    agent_runs: int
    cost_by_task: dict[str, float]
    calls_by_model: dict[str, int]
    ingestion_paths: dict[str, int]


@router.get("/activity/summary", response_model=SummaryOut)
def summary(db: DB) -> SummaryOut:
    total = db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0))) or 0.0
    n_calls = db.scalar(select(func.count()).select_from(LLMCall).where(LLMCall.ok.is_(True))) or 0
    n_failed = db.scalar(select(func.count()).select_from(LLMCall).where(LLMCall.ok.is_(False))) or 0
    unpriced = db.scalar(select(func.count()).select_from(LLMCall).where(LLMCall.priced.is_(False))) or 0
    det_runs = select(AgentRun.id).where(AgentRun.mode == "deterministic")
    det_steps = db.scalar(select(func.count()).select_from(AgentStep).where(AgentStep.run_id.in_(det_runs),
                                                                            AgentStep.kind != "llm")) or 0
    tool_steps = db.scalar(select(func.count()).select_from(AgentStep).where(AgentStep.kind == "tool")) or 0
    n_runs = db.scalar(select(func.count()).select_from(AgentRun)) or 0
    by_task = dict(db.execute(select(LLMCall.task, func.sum(LLMCall.cost_usd)).group_by(LLMCall.task)).all())
    by_model = dict(db.execute(select(LLMCall.provider + "/" + LLMCall.model, func.count())
                               .where(LLMCall.ok.is_(True)).group_by(LLMCall.provider, LLMCall.model)).all())
    paths = dict(db.execute(select(IngestionLog.path_taken, func.count())
                            .where(IngestionLog.step.in_(["legibility", "ocr", "vision", "extract", "topic"]))
                            .group_by(IngestionLog.path_taken)).all())
    return SummaryOut(total_cost_usd=round(float(total), 6), llm_calls=n_calls, llm_failed_calls=n_failed,
                      unpriced_calls=unpriced, deterministic_steps=det_steps, tool_steps=tool_steps,
                      agent_runs=n_runs, cost_by_task={k: round(float(v or 0), 6) for k, v in by_task.items()},
                      calls_by_model=by_model, ingestion_paths=paths)


class FeedItem(BaseModel):
    at: datetime
    kind: str
    text: str
    link: str = ""


@router.get("/activity/feed", response_model=list[FeedItem])
def feed(db: DB, limit: int = 20) -> list[FeedItem]:
    """Plain-language agent activity for the Today screen."""
    items: list[FeedItem] = []
    for r in db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)):
        verb = {"succeeded": "finished", "failed": "failed", "running": "is working on",
                "step_limit": "hit its step limit on"}.get(r.state, r.state)
        cost = f" · ${r.cost_usd:.4f}" if r.cost_usd else (" · no AI" if r.mode == "deterministic" else "")
        items.append(FeedItem(at=r.created_at, kind=r.agent, text=f"{r.agent.replace('_', ' ').title()} agent {verb}: "
                              f"{r.goal.splitlines()[0][:120]}{cost}", link=f"/activity?run={r.id}"))
    for e in db.scalars(select(Event).order_by(Event.created_at.desc()).limit(limit)):
        items.append(FeedItem(at=e.created_at, kind="event", text=f"Event {e.type.replace('_', ' ')} ({e.source})"))
    return sorted(items, key=lambda i: i.at, reverse=True)[:limit]
