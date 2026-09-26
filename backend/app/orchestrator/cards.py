"""Feed action cards (UX.md §4). Cards are created only here, by triggers and jobs; never by the UI.

A card carries typed actions the UI renders as one-tap buttons or inline inputs:
  {"id": "set_exam_date", "label": "Save", "type": "date", "primary": true}
Types: button (POST /cards/{id}/act), link (client navigation, `href`), upload (inline dropzone, `params`
are form fields for POST /uploads), date / text (inline input sent as `value`), credentials (account claim).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Course, Exam, Notification, Upload
from app.orchestrator.state_machines import CARD, transition

PRIORITY = {"approval": 90, "job_failed": 85, "upload_prompt": 80, "missed_class": 75, "account_claim": 70,
            "exam_date_needed": 65, "answer": 62, "catch_up_ready": 60, "exam_pack_ready": 58,
            "syllabus_wanted": 55, "past_exams_wanted": 52, "notes_filed": 45, "info": 40,
            "deadline": 64, "connect_calendar": 47, "backfill_notes": 48}

DISMISS = {"id": "dismiss", "label": "Dismiss", "type": "button"}


def action(id_: str, label: str, type_: str = "button", primary: bool = False, **extra: Any) -> dict[str, Any]:
    return {"id": id_, "label": label, "type": type_, "primary": primary, **extra}


def create_card(db: Session, kind: str, title: str, *, body: str = "", actions: list[dict[str, Any]] | None = None,
                data: dict[str, Any] | None = None, link: str = "", dedupe_key: str | None = None,
                course_id: str | None = None, action_id: str | None = None,
                priority: int | None = None) -> Notification:
    """Create a card, or return the existing one with the same dedupe key (a question is never asked twice)."""
    if dedupe_key:
        existing = db.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))
        if existing is not None:
            return existing
    card = Notification(kind=kind, title=title[:200], body=body, actions=actions or [DISMISS], data=data or {},
                        link=link, dedupe_key=dedupe_key, course_id=course_id, action_id=action_id,
                        priority=priority if priority is not None else PRIORITY.get(kind, 50))
    db.add(card)
    db.flush()
    return card


def resolve(card: Notification, status: str = "done") -> None:
    if card.status == "open":
        transition(CARD, card, status, attr="status")
        card.resolved_at = utcnow()
        card.read_at = card.read_at or utcnow()


def resolve_matching(db: Session, kinds: tuple[str, ...], **data_match: str) -> int:
    """Close open cards of these kinds whose data contains the given key/values (e.g. session_id)."""
    n = 0
    for card in db.scalars(select(Notification).where(Notification.status == "open", Notification.kind.in_(kinds))):
        if all(card.data.get(k) == v for k, v in data_match.items()):
            resolve(card)
            n += 1
    return n


# ------------------------------------------------------------------ progressive disclosure (UX §8)
def ask_exam_date(db: Session, course: Course) -> Notification | None:
    """After a subject's first class ends: 'When is the exam for this one?' (once per course)."""
    if db.scalar(select(func.count()).select_from(Exam).where(Exam.course_id == course.id)):
        return None
    return create_card(
        db, "exam_date_needed", f"When is the exam for {course.name}?",
        body="Tell me the date and I'll build your Exam Pack 14, 7 and 3 days before.",
        actions=[action("set_exam_date", "Save date", "date", primary=True), action("dismiss", "No exam")],
        data={"course_id": course.id}, dedupe_key=f"exam_date_needed:{course.id}", course_id=course.id)


def ask_past_exams(db: Session, exam: Exam, course: Course) -> Notification | None:
    has_past = db.scalar(select(func.count()).select_from(Upload).where(Upload.course_id == course.id,
                                                                        Upload.kind == "past_exam"))
    if has_past:
        return None
    return create_card(
        db, "past_exams_wanted", f"Got past {course.name} exams?",
        body="Drop them here and your practice exams will match their style and difficulty.",
        actions=[action("upload_past_exam", "Drop past exams", "upload", primary=True,
                        params={"course_id": course.id, "kind": "past_exam"}), action("dismiss", "Skip")],
        data={"course_id": course.id, "exam_id": exam.id}, dedupe_key=f"past_exams_wanted:{course.id}",
        course_id=course.id)


def ask_syllabus(db: Session, course: Course) -> Notification | None:
    if course.syllabus.strip():
        return None
    return create_card(
        db, "syllabus_wanted", f"Paste the {course.name} syllabus?",
        body="With the list of units I can tell you where the class is and what's likely in the exam. Give me the "
             "subject code and I'll fetch it from the public UPC course guide, or paste it yourself.",
        actions=[action("fetch_guide", "Fetch it", "input", primary=True,
                        placeholder="UPC subject code, e.g. 300021", input_type="text"),
                 action("save_syllabus", "Save syllabus", "text"), action("dismiss", "Skip")],
        data={"course_id": course.id}, dedupe_key=f"syllabus_wanted:{course.id}", course_id=course.id)


def create_exam_with_followups(db: Session, course: Course, exam_date: date, title: str | None = None,
                               scope_note: str = "") -> Exam:
    """Single path for creating an exam (API, card action) so follow-up cards stay consistent."""
    exam = Exam(course_id=course.id, title=title or f"{course.name} exam", exam_date=exam_date, scope_note=scope_note)
    db.add(exam)
    db.flush()
    resolve_matching(db, ("exam_date_needed",), course_id=course.id)
    ask_past_exams(db, exam, course)
    return exam
