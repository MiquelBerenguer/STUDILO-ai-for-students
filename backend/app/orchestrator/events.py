"""Events are facts ("class ended", "upload completed"). The orchestrator maps each event to a job.

Automatic triggers (scheduler) and manual UI actions call the same `emit()`, so they behave identically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Event, Job, TriggerLog

EventType = Literal[
    "class_ended", "class_slot_passed_without_upload", "upload_completed", "exam_approaching", "exam_requested",
    "catch_up_requested", "question_asked", "calendar_sync_due",
]

EVENT_TO_JOB: dict[str, str] = {
    "class_ended": "class_ended",
    "class_slot_passed_without_upload": "missed_upload",
    "upload_completed": "process_upload",
    "exam_approaching": "build_exam_pack",
    "exam_requested": "build_exam_pack",
    "catch_up_requested": "catch_up",
    "question_asked": "answer_question",
    "calendar_sync_due": "sync_calendar",
}


def emit(db: Session, type_: EventType, payload: dict[str, Any], source: str = "system",
         run_after: datetime | None = None) -> Job:
    """Record the event and enqueue its job, in the caller's (user-scoped) transaction."""
    event = Event(type=type_, payload=payload, source=source)
    db.add(event)
    db.flush()
    job = Job(type=EVENT_TO_JOB[type_], payload={**payload, "event": type_, "source": source},
              event_id=event.id, run_after=run_after or utcnow())
    db.add(job)
    db.flush()
    return job


def once(db: Session, key: str) -> bool:
    """Idempotency guard for automatic triggers. True the first time a key is seen for this user."""
    try:
        with db.begin_nested():
            db.add(TriggerLog(key=key))
            db.flush()
        return True
    except IntegrityError:
        return False
