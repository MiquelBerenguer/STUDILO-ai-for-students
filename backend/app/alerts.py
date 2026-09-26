"""Pending alerts: what needs the student now, as pure rules over a snapshot of their data.

Shared by the Overview ("Pending") and Ask Novi (the `/ask?context=<ref>` handoff). Change a rule here and
both surfaces stay consistent. Everything below `load_snapshot` is pure: no I/O, no clock, no LLM.

Refs (stable ids used in URLs):
  missing_notes:<session_id> | missing_notes:<slot_id>@<YYYY-MM-DD> (class held, no session row yet)
  task_due:<assignment_id> · exam_prep:<exam_id> · pending:<card_id> · pending:all
  setup:<courses,schedule,exam_dates>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    ClassSession,
    ClassSlot,
    Course,
    Exam,
    ExamAttempt,
    ExamPack,
    NoteSection,
    Notification,
    PracticeExam,
    Topic,
)
from app.orchestrator import cards

AlertType = Literal["missing_notes", "task_due", "exam_prep", "approval", "job_failed"]
SetupPiece = Literal["courses", "schedule", "exam_dates"]

MISSING_NOTES_DAYS = 7  # older gaps only affect progress, never Pending
TASK_AHEAD_DAYS = 3
TASK_OVERDUE_DAYS = 7
EXAM_PREP_DAYS = 14
MAX_HISTORY_DAYS = 400  # a slot created long ago never makes us walk years of dates
NOTES_STATES = frozenset({"uploaded", "processed"})
CARD_ALERTS: dict[str, AlertType] = {"approval": "approval", "job_failed": "job_failed"}
SETUP_LABELS: dict[SetupPiece, str] = {"courses": "your subjects", "schedule": "your timetable",
                                       "exam_dates": "your exam dates"}


# ------------------------------------------------------------------ snapshot (plain values, no ORM)
@dataclass(frozen=True)
class CourseIn:
    id: str
    name: str
    color: str = "#6366f1"
    syllabus: str = ""


@dataclass(frozen=True)
class SlotIn:
    id: str
    course_id: str
    weekday: int
    start_time: str
    end_time: str
    created_at: datetime
    location: str = ""


@dataclass(frozen=True)
class SessionIn:
    id: str
    course_id: str
    slot_id: str | None
    session_date: date
    state: str


@dataclass(frozen=True)
class ExamIn:
    id: str
    course_id: str
    title: str
    exam_date: date


@dataclass(frozen=True)
class AssignmentIn:
    id: str
    course_id: str
    title: str
    due_date: date
    done: bool = False
    due_at: datetime | None = None


@dataclass(frozen=True)
class CardIn:
    id: str
    kind: str
    title: str
    created_at: datetime
    body: str = ""
    actions: tuple[dict[str, Any], ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    course_id: str | None = None


@dataclass(frozen=True)
class AttemptIn:
    course_id: str
    exam_id: str | None
    submitted_at: datetime


@dataclass(frozen=True)
class TopicIn:
    id: str
    course_id: str
    title: str
    has_notes: bool


@dataclass(frozen=True)
class Snapshot:
    now: datetime  # aware UTC
    tz: str
    semester_start: date | None = None
    semester_end: date | None = None
    courses: tuple[CourseIn, ...] = ()
    slots: tuple[SlotIn, ...] = ()
    sessions: tuple[SessionIn, ...] = ()
    exams: tuple[ExamIn, ...] = ()
    assignments: tuple[AssignmentIn, ...] = ()
    cards: tuple[CardIn, ...] = ()  # open cards only
    attempts: tuple[AttemptIn, ...] = ()  # submitted practice attempts only
    topics: tuple[TopicIn, ...] = ()

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def today(self) -> date:
        return self.now.astimezone(self.zone).date()

    def local(self, d: date, hhmm: str) -> datetime:
        h, m = (int(x) for x in hhmm.split(":"))
        return datetime.combine(d, time(h, m), tzinfo=self.zone).astimezone(UTC)

    def course(self, course_id: str) -> CourseIn | None:
        return next((c for c in self.courses if c.id == course_id), None)

    def course_name(self, course_id: str) -> str:
        c = self.course(course_id)
        return c.name if c else "your course"

    def in_semester(self, d: date) -> bool:
        return not ((self.semester_start and d < self.semester_start) or (self.semester_end and d > self.semester_end))


# ------------------------------------------------------------------ classes held (shared primitive)
@dataclass(frozen=True)
class HeldClass:
    slot: SlotIn
    session_date: date
    starts_at: datetime
    ends_at: datetime
    session: SessionIn | None

    @property
    def has_notes(self) -> bool:
        return self.session is not None and self.session.state in NOTES_STATES

    @property
    def course_id(self) -> str:
        return self.slot.course_id


def held_classes(snap: Snapshot, since: date | None = None) -> list[HeldClass]:
    """Every slot occurrence that already ended, counted from the day the slot was added (and the semester start).

    Classes before a slot existed are not counted: Novi wasn't following them, so they can't be "missing".
    """
    by_key = {(s.slot_id, s.session_date): s for s in snap.sessions if s.slot_id}
    today = snap.today
    out: list[HeldClass] = []
    for slot in snap.slots:
        first = max(slot.created_at.astimezone(snap.zone).date(), today - timedelta(days=MAX_HISTORY_DAYS))
        if snap.semester_start:
            first = max(first, snap.semester_start)
        if since:
            first = max(first, since)
        d = first + timedelta(days=(slot.weekday - first.weekday()) % 7)
        while d <= today:
            if snap.in_semester(d):
                ends = snap.local(d, slot.end_time)
                if slot.created_at < ends <= snap.now:
                    out.append(HeldClass(slot, d, snap.local(d, slot.start_time), ends, by_key.get((slot.id, d))))
            d += timedelta(days=7)
    out.sort(key=lambda h: h.ends_at)
    return out


def day_label(snap: Snapshot, d: date, possessive: bool = False) -> str:
    """"today" / "yesterday" / "Monday" (or "today's", "Monday's")."""
    delta = (snap.today - d).days
    word = "today" if delta == 0 else "yesterday" if delta == 1 else d.strftime("%A") if 1 < delta < 7 \
        else d.strftime("%a %d %b")
    return f"{word}'s" if possessive else word


def due_moment(snap: Snapshot, a: AssignmentIn) -> datetime:
    return a.due_at or snap.local(a.due_date, "23:59")


def submitted_practice(snap: Snapshot, course_id: str) -> int:
    return sum(1 for a in snap.attempts if a.course_id == course_id)


# ------------------------------------------------------------------ alerts
@dataclass(frozen=True)
class Alert:
    ref: str
    type: AlertType
    tier: int  # 1 = most urgent
    title: str
    reason: str
    seed_message: str  # the first message Novi starts from, in the student's voice
    sort_key: float
    course_id: str | None = None
    due_at: datetime | None = None
    card_id: str | None = None
    session_id: str | None = None
    slot_id: str | None = None
    session_date: date | None = None
    assignment_id: str | None = None
    exam_id: str | None = None
    actions: tuple[dict[str, Any], ...] = ()  # inline one-tap actions (same shape as card actions)


def _card_for(snap: Snapshot, kinds: tuple[str, ...], key: str, value: str) -> CardIn | None:
    return next((c for c in snap.cards if c.kind in kinds and c.data.get(key) == value), None)


def _missing_notes(snap: Snapshot) -> list[Alert]:
    out = []
    for h in held_classes(snap, since=snap.today - timedelta(days=MISSING_NOTES_DAYS - 1)):  # today + 6 days back
        if h.has_notes:
            continue
        name = snap.course_name(h.course_id)
        sid = h.session.id if h.session else None
        card = _card_for(snap, ("upload_prompt", "missed_class"), "session_id", sid) if sid else None
        params: dict[str, str] = {"course_id": h.course_id, "kind": "notes"}
        if sid:
            params["class_session_id"] = sid
        else:
            params |= {"slot_id": h.slot.id, "session_date": h.session_date.isoformat()}
        label = day_label(snap, h.session_date, possessive=True)
        ended = h.ends_at.astimezone(snap.zone)
        reason = f"Class ended at {ended:%H:%M}" if h.session_date == snap.today else \
            f"Class on {h.session_date:%a %d %b}, {h.slot.start_time}–{h.slot.end_time}"
        out.append(Alert(
            ref=f"missing_notes:{sid}" if sid else f"missing_notes:{h.slot.id}@{h.session_date.isoformat()}",
            type="missing_notes", tier=4, title=f"Notes for {label} {name} class", reason=reason,
            seed_message=f"Help me with the notes from {label} {name} class.",
            sort_key=-h.ends_at.timestamp(), course_id=h.course_id, due_at=None, card_id=card.id if card else None,
            session_id=sid, slot_id=h.slot.id, session_date=h.session_date,
            actions=(cards.action("drop_notes", "Drop notes", "upload", primary=True, params=params),)))
    return out


def _tasks(snap: Snapshot) -> list[Alert]:
    out = []
    today = snap.today
    for a in snap.assignments:
        if a.done or not (today - timedelta(days=TASK_OVERDUE_DAYS) <= a.due_date <= today + timedelta(days=TASK_AHEAD_DAYS)):
            continue
        due = due_moment(snap, a)
        local = due.astimezone(snap.zone)
        days = (a.due_date - today).days
        when = "was due " + day_label(snap, a.due_date) if due < snap.now else \
            f"due today at {local:%H:%M}" if days == 0 else "due tomorrow" if days == 1 else f"due {a.due_date:%A}"
        card = _card_for(snap, ("deadline",), "assignment_id", a.id)
        out.append(Alert(
            ref=f"task_due:{a.id}", type="task_due", tier=1 if due <= snap.now + timedelta(hours=24) else 3,
            title=a.title, reason=f"{snap.course_name(a.course_id)} · {when}",
            seed_message=f"Help me get “{a.title}” done. It's {when}.", sort_key=due.timestamp(),
            course_id=a.course_id, due_at=due, card_id=card.id if card else None, assignment_id=a.id,
            actions=(cards.action("mark_done", "Mark done", primary=True),)))
    return out


def _exam_prep(snap: Snapshot) -> list[Alert]:
    out = []
    for e in snap.exams:
        days = (e.exam_date - snap.today).days
        if not 0 <= days <= EXAM_PREP_DAYS or submitted_practice(snap, e.course_id):
            continue
        name = snap.course_name(e.course_id)
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        at = snap.local(e.exam_date, "09:00")
        out.append(Alert(
            ref=f"exam_prep:{e.id}", type="exam_prep", tier=1 if days <= 1 else 5,
            title=f"Practice for your {e.title}", reason=f"Exam {when} · no practice exam yet",
            seed_message=f"Make me a practice exam for {name}.", sort_key=at.timestamp(),
            course_id=e.course_id, due_at=at, exam_id=e.id))
    return out


def _card_alerts(snap: Snapshot) -> list[Alert]:
    out = []
    for c in snap.cards:
        kind = CARD_ALERTS.get(c.kind)
        if kind is None:
            continue
        seed = (f"Should I approve this? {c.title}" if kind == "approval"
                else f"Something failed: {c.title} Can you help me fix it?")
        out.append(Alert(
            ref=f"pending:{c.id}", type=kind, tier=2, title=c.title, reason=_first_sentence(c.body),
            seed_message=seed, sort_key=c.created_at.timestamp(), course_id=c.course_id, card_id=c.id,
            actions=tuple(a for a in c.actions if a.get("id") != "dismiss" and a.get("type") == "button")))
    return out


def _first_sentence(text: str, limit: int = 140) -> str:
    s = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0] if text.strip() else ""
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def compute_alerts(snap: Snapshot) -> list[Alert]:
    """All pending alerts, most urgent first: tier, then time (missing notes: most recent first)."""
    alerts = _tasks(snap) + _exam_prep(snap) + _card_alerts(snap) + _missing_notes(snap)
    return sorted(alerts, key=lambda a: (a.tier, a.sort_key, a.ref))


def setup_missing(snap: Snapshot) -> list[SetupPiece]:
    pieces: list[tuple[SetupPiece, bool]] = [("courses", bool(snap.courses)), ("schedule", bool(snap.slots)),
                                             ("exam_dates", bool(snap.exams))]
    return [p for p, ok in pieces if not ok]


# ------------------------------------------------------------------ Ask Novi handoff
@dataclass(frozen=True)
class AlertContext:
    ref: str
    type: str  # an AlertType, "setup" or "pending_all"
    title: str
    reason: str
    seed_message: str
    alerts: tuple[Alert, ...] = ()  # the alert itself, or every alert for pending:all
    setup_missing: tuple[SetupPiece, ...] = ()


def resolve_context(snap: Snapshot, ref: str) -> AlertContext | None:
    """What Ask Novi should start working on for a ref. None = unknown or already resolved."""
    kind, _, value = ref.partition(":")
    if kind == "pending" and value == "all":
        alerts = tuple(compute_alerts(snap))
        return AlertContext(ref=ref, type="pending_all", title="Everything pending",
                            reason=f"{len(alerts)} thing{'s' if len(alerts) != 1 else ''} pending",
                            seed_message="What do I have pending?", alerts=alerts)
    if kind == "setup":
        missing = tuple(setup_missing(snap))
        if not missing:
            return None
        what = _join([SETUP_LABELS[p] for p in missing])
        return AlertContext(ref=ref, type="setup", title="Finish setting up", reason=f"Missing: {what}",
                            seed_message=f"Help me finish setting up: add {what}.", setup_missing=missing)
    alert = next((a for a in compute_alerts(snap) if a.ref == ref), None)
    if alert is None:
        return None
    return AlertContext(ref=ref, type=alert.type, title=alert.title, reason=alert.reason,
                        seed_message=alert.seed_message, alerts=(alert,))


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ------------------------------------------------------------------ loader (the only I/O in this module)
def load_snapshot(db: Session, *, now: datetime, tz: str, semester_start: date | None = None,
                  semester_end: date | None = None) -> Snapshot:
    """Read the user's data through the user-scoped session (scoping is enforced by app.db.engine)."""
    attempts = db.execute(
        select(ExamPack.course_id, ExamPack.exam_id, ExamAttempt.submitted_at)
        .join(PracticeExam, PracticeExam.id == ExamAttempt.practice_exam_id)
        .join(ExamPack, ExamPack.id == PracticeExam.pack_id)
        .where(ExamAttempt.submitted_at.is_not(None))).all()
    noted = set(db.scalars(select(NoteSection.topic_id).distinct()))
    return Snapshot(
        now=now, tz=tz, semester_start=semester_start, semester_end=semester_end,
        courses=tuple(CourseIn(c.id, c.name, c.color, c.syllabus)
                      for c in db.scalars(select(Course).order_by(Course.created_at))),
        slots=tuple(SlotIn(s.id, s.course_id, s.weekday, s.start_time, s.end_time, s.created_at, s.location)
                    for s in db.scalars(select(ClassSlot).order_by(ClassSlot.weekday, ClassSlot.start_time))),
        sessions=tuple(SessionIn(s.id, s.course_id, s.slot_id, s.session_date, s.state)
                       for s in db.scalars(select(ClassSession).where(
                           ClassSession.session_date >= now.date() - timedelta(days=MAX_HISTORY_DAYS + 1)))),
        exams=tuple(ExamIn(e.id, e.course_id, e.title, e.exam_date)
                    for e in db.scalars(select(Exam).order_by(Exam.exam_date))),
        assignments=tuple(AssignmentIn(a.id, a.course_id, a.title, a.due_date, a.done, a.due_at)
                          for a in db.scalars(select(Assignment).where(Assignment.done.is_(False)))),
        cards=tuple(CardIn(c.id, c.kind, c.title, c.created_at, c.body, tuple(c.actions), dict(c.data), c.course_id)
                    for c in db.scalars(select(Notification).where(Notification.status == "open"))),
        attempts=tuple(AttemptIn(course_id, exam_id, submitted) for course_id, exam_id, submitted in attempts),
        topics=tuple(TopicIn(t.id, t.course_id, t.title, t.id in noted) for t in db.scalars(select(Topic))),
    )
