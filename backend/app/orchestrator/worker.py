"""Orchestrator: DB-backed job queue + asyncio workers + scheduler tick (DECISIONS D-02).

The `jobs` table is the only source of job state; the UI reads it directly.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select, update

from app.agents.base import ToolContext
from app.agents.planner import PlannerAgent
from app.config.settings import get_settings
from app.db.base import utcnow
from app.db.engine import scoped_session_for, system_session_ctx
from app.db.models import Job, User
from app.llm.client import get_llm
from app.llm.types import LLMUnavailable
from app.orchestrator import cards
from app.orchestrator.handlers import HANDLERS
from app.orchestrator.state_machines import JOB

log = logging.getLogger(__name__)

# Pipelines the student is waiting on: a failure becomes a feed card with Retry (UX.md §4).
FAILURE_CARDS = {
    "process_upload": "I couldn't process your upload",
    "build_exam_pack": "I couldn't build the Exam Pack",
    "catch_up": "I couldn't prepare the catch-up",
    "answer_question": "I couldn't answer that",
}


def claim_next(now: datetime | None = None) -> tuple[str, str] | None:
    """Atomically move one due job from queued to running. Returns (job_id, user_id)."""
    now = now or utcnow()
    with system_session_ctx() as db:
        candidates = db.execute(select(Job.id, Job.user_id).where(Job.state == "queued", Job.run_after <= now)
                                .order_by(Job.run_after, Job.created_at).limit(5)).all()
        for job_id, user_id in candidates:
            JOB.check("queued", "running")
            res = db.execute(update(Job).where(Job.id == job_id, Job.state == "queued")
                             .values(state="running", started_at=utcnow(), attempts=Job.attempts + 1))
            if res.rowcount == 1:
                return job_id, user_id
    return None


async def run_job(job_id: str, user_id: str, now: datetime | None = None) -> str:
    """Run one claimed job with a session scoped to the job's owner. Returns the final state."""
    db = scoped_session_for(user_id)
    try:
        job = db.get(Job, job_id)
        if job is None:
            return "missing"

        def progress(msg: str) -> None:
            job.progress = msg[:300]
            db.commit()

        ctx = ToolContext(user_id=user_id, db=db, llm=get_llm(), now=now or utcnow(), job_id=job.id,
                          progress=progress)
        handler = HANDLERS.get(job.type)
        if handler is None:
            raise RuntimeError(f"no handler for job type {job.type!r}")
        try:
            result = await handler(ctx, dict(job.payload))
        except Exception as exc:
            log.exception("job %s (%s) failed", job.id, job.type)
            db.rollback()
            job = db.get(Job, job_id)
            assert job is not None
            JOB.check(job.state, "failed")
            job.state, job.error, job.finished_at = "failed", f"{type(exc).__name__}: {exc}"[:4000], utcnow()
            if job.type in FAILURE_CARDS:
                body = ("The AI models were busy or unavailable just now (details are in Activity). Retry in a minute."
                        if isinstance(exc, LLMUnavailable) else str(exc)[:400])
                cards.create_card(db, "job_failed", FAILURE_CARDS[job.type], body=body,
                                  actions=[cards.action("retry", "Retry", primary=True), cards.DISMISS],
                                  data={"job_id": job.id, "job_type": job.type}, dedupe_key=f"job_failed:{job.id}")
            db.commit()
            return "failed"
        job = db.get(Job, job_id)
        assert job is not None
        JOB.check(job.state, "succeeded")
        job.state, job.result, job.finished_at = "succeeded", result or {}, utcnow()
        db.commit()
        return "succeeded"
    finally:
        db.close()


async def drain(now: datetime | None = None, max_jobs: int = 100) -> int:
    """Run due jobs until none are left (used by tests and the simulate endpoint)."""
    n = 0
    while n < max_jobs:
        claimed = claim_next(now)
        if claimed is None:
            break
        await run_job(*claimed, now=now)
        n += 1
    return n


async def tick(now: datetime | None = None, user_id: str | None = None) -> dict[str, list[str]]:
    """Scheduler tick: let the Planner decide for each active user (or just one)."""
    now = now or utcnow()
    with system_session_ctx() as db:
        q = select(User.id).where(User.journey_state == "active")
        if user_id:
            q = q.where(User.id == user_id)
        user_ids = list(db.scalars(q))
    out: dict[str, list[str]] = {}
    for uid in user_ids:
        db = scoped_session_for(uid)
        try:
            ctx = ToolContext(user_id=uid, db=db, llm=get_llm(), now=now)
            out[uid] = await PlannerAgent().plan(ctx)
        except Exception:
            log.exception("planner failed for user %s", uid)
            db.rollback()
        finally:
            db.close()
    return out


class Orchestrator:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()
        self._running: set[asyncio.Task[str]] = set()

    def start(self) -> None:
        with system_session_ctx() as db:  # jobs interrupted by a restart go back to the queue
            db.execute(update(Job).where(Job.state == "running").values(state="queued"))
        self._tasks = [asyncio.create_task(self._worker_loop()), asyncio.create_task(self._scheduler_loop())]
        log.info("orchestrator started")

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _worker_loop(self) -> None:
        # Each job runs in its own thread + event loop. SQLite write locks are then waited on per
        # thread (busy_timeout) instead of blocking one shared event loop while another job holds the lock.
        conc = get_settings().WORKER_CONCURRENCY
        while not self._stop.is_set():
            try:
                while len(self._running) < conc and (claimed := claim_next()):
                    task = asyncio.create_task(asyncio.to_thread(_run_job_in_thread, *claimed))
                    self._running.add(task)
                    task.add_done_callback(self._running.discard)
            except Exception:
                log.exception("worker loop error")
            await asyncio.sleep(1.0)

    async def _scheduler_loop(self) -> None:
        interval = get_settings().SCHEDULER_INTERVAL_SECONDS
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(lambda: asyncio.run(tick()))
            except Exception:
                log.exception("scheduler tick error")
            await asyncio.sleep(interval)


def _run_job_in_thread(job_id: str, user_id: str) -> str:
    return asyncio.run(run_job(job_id, user_id))
