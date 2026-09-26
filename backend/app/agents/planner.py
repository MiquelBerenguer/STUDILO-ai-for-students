"""Planner/Scheduler agent: decides what should happen next for each course (deterministic policy, D-05).

Called by the scheduler tick (or the "simulate" endpoint with an injected clock). It only records an
agent run when it actually decides to do something, so idle ticks do not flood the Activity screen.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.agents.base import AgentTrace, ToolContext
from app.db.models import CalendarFeed, ClassSession, ClassSlot
from app.integrations.calendar_feed import due_for_sync
from app.orchestrator.events import emit, once
from app.orchestrator.timeutil import local_dt, local_today
from app.tools.planner import PLANNER_TOOLS as T

EXAM_THRESHOLDS = (14, 7, 3)


class PlannerAgent:
    name = "planner"

    def __init__(self) -> None:
        self._trace: AgentTrace | None = None
        self.actions: list[str] = []

    def _t(self, ctx: ToolContext, goal: str) -> AgentTrace:
        if self._trace is None:
            self._trace = AgentTrace(ctx, self.name, "deterministic", goal)
        return self._trace

    async def plan(self, ctx: ToolContext) -> list[str]:
        now = ctx.now
        sched = await T["get_schedule"].invoke(ctx, {})
        tz = sched["timezone"]
        today = local_today(now, tz)
        sem_start: date | None = sched["semester_start"]
        sem_end: date | None = sched["semester_end"]
        goal = f"Scheduler tick at {now.isoformat(timespec='minutes')}"

        # 1) class slots that ended -> class_ended
        for slot in sched["slots"]:
            for d in (today - timedelta(days=1), today):
                if d.weekday() != slot["weekday"] or (sem_start and d < sem_start) or (sem_end and d > sem_end):
                    continue
                ends = local_dt(d, slot["end"], tz)
                if ends > now or not once(ctx.db, f"class_ended:{slot['slot_id']}:{d.isoformat()}"):
                    continue
                trace = self._t(ctx, goal)
                trace.decision("class_ended", {"course": slot["course"], "date": d.isoformat(), "end": slot["end"]})
                emit(ctx.db, "class_ended", {"slot_id": slot["slot_id"], "session_date": d.isoformat()}, "scheduler")
                self.actions.append(f"class_ended {slot['course']} {d}")

        # 2) sessions still without notes N hours after the class -> class_slot_passed_without_upload
        threshold = now - timedelta(hours=int(sched["missed_after_hours"]))
        waiting = ctx.db.scalars(select(ClassSession).where(ClassSession.state == "awaiting_upload",
                                                           ClassSession.ends_at <= threshold))
        for s in waiting:
            if once(ctx.db, f"missed:{s.id}"):
                self._t(ctx, goal).decision("missed_upload", {"session_id": s.id, "date": s.session_date.isoformat()})
                emit(ctx.db, "class_slot_passed_without_upload", {"session_id": s.id}, "scheduler")
                self.actions.append(f"missed {s.id}")

        # 3) exams at T-14 / T-7 / T-3 -> exam_approaching (once per threshold; crossing several emits once)
        for exam in await T["get_exam_dates"].invoke(ctx, {}):
            days = exam["days_left"]
            crossed = [t for t in EXAM_THRESHOLDS if 0 <= days <= t]
            if not crossed:
                continue
            fresh = [t for t in crossed if once(ctx.db, f"exam_approaching:{exam['exam_id']}:T-{t}")]
            if fresh:
                th = min(fresh)
                self._t(ctx, goal).decision("exam_approaching", {"exam": exam["title"], "days_left": days,
                                                                 "threshold": f"T-{th}"})
                emit(ctx.db, "exam_approaching", {"exam_id": exam["exam_id"], "threshold": th}, "scheduler")
                self.actions.append(f"exam_approaching {exam['title']} T-{th}")

        # 4) connected calendars (Moodle/Atenea export) -> daily refresh
        for feed in ctx.db.scalars(select(CalendarFeed)):
            if due_for_sync(feed, now) and once(ctx.db, f"calendar_sync:{feed.id}:{today.isoformat()}"):
                emit(ctx.db, "calendar_sync_due", {"feed_id": feed.id}, "scheduler")
                self.actions.append(f"calendar_sync {feed.label}")

        if self._trace:
            self._trace.finish("succeeded", "; ".join(self.actions))
        ctx.db.commit()
        return self.actions


def slot_times(slot: ClassSlot, d: date, tz: str) -> tuple[datetime, datetime]:
    return local_dt(d, slot.start_time, tz), local_dt(d, slot.end_time, tz)
