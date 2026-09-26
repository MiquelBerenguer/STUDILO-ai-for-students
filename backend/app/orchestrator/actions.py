"""Autonomy with control (UX.md §7): applied actions are undoable; high-impact ones are proposals.

Low risk  → applied immediately, recorded with the snapshot (`effects`) needed to undo it.
High risk → recorded as `proposed` with an approval card; nothing changes until approved.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    AgentAction,
    ClassSession,
    Course,
    CourseMemory,
    Exam,
    ExamAttempt,
    ExamPack,
    NoteSection,
    Notification,
    OpenQuestion,
    PracticeExam,
    SectionSource,
    Topic,
    TopicDependency,
    TriggerLog,
    Upload,
)
from app.orchestrator import cards
from app.orchestrator.state_machines import ACTION, CLASS_SESSION, UPLOAD, transition
from app.tools import store

UNDO_WINDOW = timedelta(days=7)

AUTONOMY_POLICY = [
    {"risk": "low", "action": "File your notes into topics and create topics", "mode": "I do it, you can undo"},
    {"risk": "low", "action": "Update course memory (sessions, pace, open questions)", "mode": "I do it, you can undo"},
    {"risk": "low", "action": "Flag classes without notes as missed", "mode": "I do it; a late upload clears it"},
    {"risk": "low", "action": "Build or refresh Exam Packs at T-14 / T-7 / T-3", "mode": "I do it, you can undo"},
    {"risk": "high", "action": "Change an exam's date or scope", "mode": "I ask first"},
    {"risk": "high", "action": "Delete content", "mode": "I ask first"},
]


class UndoRefused(Exception):
    """User-visible reason why an action can't be undone (or approved) any more."""


# ------------------------------------------------------------------ recording
def record_file_notes(db: Session, upload: Upload, job_id: str | None, effects: dict[str, Any], title: str) -> AgentAction:
    act = AgentAction(kind="file_notes", risk="low", status="applied", title=title, effects=effects,
                      job_id=job_id, upload_id=upload.id, payload={"upload_id": upload.id})
    db.add(act)
    db.flush()
    return act


def record_pack(db: Session, pack: ExamPack, job_id: str | None, title: str) -> AgentAction:
    act = AgentAction(kind="build_pack", risk="low", status="applied", title=title, job_id=job_id,
                      payload={"pack_id": pack.id}, effects={"pack_id": pack.id})
    db.add(act)
    db.flush()
    return act


def propose_exam_date(db: Session, exam: Exam, course: Course, new_date: date, request: str) -> tuple[AgentAction, Notification]:
    title = f"Move {exam.title} from {exam.exam_date:%d %b} to {new_date:%d %b}?"
    act = AgentAction(kind="change_exam_date", risk="high", status="proposed", title=title,
                      payload={"exam_id": exam.id, "new_date": new_date.isoformat(), "request": request})
    db.add(act)
    db.flush()
    card = cards.create_card(
        db, "approval", title,
        body="Changing an exam date is high impact, so I'm asking first. I'll re-plan the Exam Pack builds "
             "(T-14 / T-7 / T-3) for the new date.",
        actions=[cards.action("approve", "Approve", primary=True), cards.action("reject", "Reject")],
        data={"exam_id": exam.id, "request": request}, action_id=act.id, course_id=course.id)
    return act, card


# ------------------------------------------------------------------ approve / reject
def approve(db: Session, act: AgentAction) -> str:
    if act.status != "proposed":
        raise UndoRefused(f"This proposal is already {act.status}.")
    if act.kind == "change_exam_date":
        exam = db.get(Exam, act.payload["exam_id"])
        if exam is None:
            raise UndoRefused("That exam no longer exists.")
        previous = exam.exam_date
        exam.exam_date = date.fromisoformat(act.payload["new_date"])
        _replan_exam_triggers(db, exam)
        act.effects = {"exam_id": exam.id, "previous_date": previous.isoformat()}
        transition(ACTION, act, "applied", attr="status")
        act.resolved_at = utcnow()
        return f"Done — {exam.title} is now on {exam.exam_date:%d %b}. Exam Pack builds re-planned."
    raise UndoRefused(f"Unknown proposal type {act.kind}")


def reject(db: Session, act: AgentAction) -> str:
    if act.status != "proposed":
        raise UndoRefused(f"This proposal is already {act.status}.")
    transition(ACTION, act, "rejected", attr="status")
    act.resolved_at = utcnow()
    return "Okay, nothing changed."


def _replan_exam_triggers(db: Session, exam: Exam) -> None:
    """Forget which T-14/7/3 triggers fired so the Planner re-evaluates them against the new date."""
    db.execute(delete(TriggerLog).where(TriggerLog.key.like(f"exam_approaching:{exam.id}:%")))


# ------------------------------------------------------------------ undo
async def undo(db: Session, user_id: str, act: AgentAction) -> str:
    if act.status != "applied":
        raise UndoRefused(f"Nothing to undo: this action is {act.status}.")
    if utcnow() - act.created_at > UNDO_WINDOW:
        raise UndoRefused("Undo is only available for 7 days.")
    if act.kind == "file_notes":
        msg = await _undo_file_notes(db, user_id, act)
    elif act.kind == "build_pack":
        msg = _undo_pack(db, act)
    elif act.kind == "change_exam_date":
        exam = db.get(Exam, act.effects.get("exam_id"))
        if exam is None:
            raise UndoRefused("That exam no longer exists.")
        exam.exam_date = date.fromisoformat(act.effects["previous_date"])
        _replan_exam_triggers(db, exam)
        msg = f"Restored {exam.title} to {exam.exam_date:%d %b}."
    else:
        raise UndoRefused(f"Unknown action type {act.kind}")
    transition(ACTION, act, "undone", attr="status")
    act.resolved_at = utcnow()
    for card in db.scalars(select(Notification).where(Notification.action_id == act.id)):
        cards.resolve(card)
    return msg


def _undo_pack(db: Session, act: AgentAction) -> str:
    pack = db.get(ExamPack, act.effects.get("pack_id"))
    if pack is None:
        return "That pack was already removed."
    practice_ids = [p.id for p in db.scalars(select(PracticeExam).where(PracticeExam.pack_id == pack.id))]
    if practice_ids and db.scalar(select(ExamAttempt).where(ExamAttempt.practice_exam_id.in_(practice_ids))):
        raise UndoRefused("You already took a practice exam from this pack, so I kept it.")
    db.delete(pack)
    return f"Removed Exam Pack v{pack.version}."


async def _undo_file_notes(db: Session, user_id: str, act: AgentAction) -> str:
    fx = act.effects
    upload = db.get(Upload, fx.get("upload_id") or act.upload_id)
    if upload is None:
        raise UndoRefused("The upload no longer exists.")
    # 1) refuse when later work built on top of this filing
    for sid in fx.get("created_sections", []):
        sec = db.get(NoteSection, sid)
        if sec is None:
            continue
        others = db.scalars(select(SectionSource.upload_id).where(SectionSource.section_id == sid,
                                                                  SectionSource.upload_id != upload.id)).all()
        if sec.version > 1 or others:
            raise UndoRefused(f"“{sec.heading}” was changed by a later upload, so I can't safely undo this.")
    for sid, snap in fx.get("revised", {}).items():
        sec = db.get(NoteSection, sid)
        if sec is not None and sec.version != snap["after_version"]:
            raise UndoRefused(f"“{sec.heading}” was changed again after this upload, so I can't safely undo this.")
    # 2) remove sections this upload created, restore the ones it revised
    for sid in fx.get("created_sections", []):
        sec = db.get(NoteSection, sid)
        if sec is not None:
            store.delete_section(db, sec)
    db.execute(delete(SectionSource).where(SectionSource.upload_id == upload.id))
    restored = []
    for sid, snap in fx.get("revised", {}).items():
        sec = db.get(NoteSection, sid)
        if sec is not None:
            sec.heading, sec.content_md, sec.version = snap["heading"], snap["content_md"], snap["before_version"]
            restored.append(sec)
    # 3) topics it created, if now empty and not used by another upload
    for tid in fx.get("created_topics", []):
        topic = db.get(Topic, tid)
        if topic is None:
            continue
        has_sections = db.scalar(select(NoteSection.id).where(NoteSection.topic_id == tid).limit(1))
        used = db.scalar(select(Upload.id).where(Upload.topic_id == tid, Upload.id != upload.id).limit(1))
        if not has_sections and not used:
            db.delete(topic)
    # 4) course memory
    for dep_id in fx.get("created_dependencies", []):
        dep = db.get(TopicDependency, dep_id)
        if dep is not None:
            db.delete(dep)
    db.execute(delete(OpenQuestion).where(OpenQuestion.source_upload_id == upload.id))
    sess_snap = fx.get("session")
    if sess_snap:
        session = db.get(ClassSession, sess_snap["id"])
        if session is not None:
            session.summary_md, session.topic_ids = sess_snap["summary_md"], sess_snap["topic_ids"]
            if session.state != sess_snap["state"] and CLASS_SESSION.can(session.state, sess_snap["state"]):
                transition(CLASS_SESSION, session, sess_snap["state"])
    mem_snap = fx.get("memory")
    if mem_snap:
        mem = db.scalar(select(CourseMemory).where(CourseMemory.course_id == upload.course_id))
        if mem is not None:
            mem.topics_per_week, mem.syllabus_position, mem.pace_note = (
                mem_snap["topics_per_week"], mem_snap["syllabus_position"], mem_snap["pace_note"])
    # 5) the upload itself
    if UPLOAD.can(upload.state, "undone"):
        transition(UPLOAD, upload, "undone")
    upload.topic_id = None
    upload.status_message = "Undone — removed from your notes"
    db.flush()
    for sec in restored:
        await store.reindex_section(db, user_id, sec)
    return f"Undone — {upload.filename} was removed from your notes and course memory was restored."


def snapshot_session_and_memory(db: Session, session: ClassSession, course_id: str) -> dict[str, Any]:
    mem = db.scalar(select(CourseMemory).where(CourseMemory.course_id == course_id))
    return {
        "session": {"id": session.id, "summary_md": session.summary_md, "topic_ids": list(session.topic_ids),
                    "state": session.state},
        "memory": None if mem is None else {"topics_per_week": mem.topics_per_week,
                                            "syllabus_position": mem.syllabus_position, "pace_note": mem.pace_note},
    }
