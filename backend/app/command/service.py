"""Command bar: route a natural-language request to the right agent, job or proposal (UX.md §6).

Deterministic parsing first (`parse.py`). Only when no rule matches, a JEV-style typed classification runs on
the cheap model (`jev_classification`): the intent is a closed Literal, slots are typed and Pydantic-validated,
one retry, then "unknown". Every request is recorded as an event.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.command.parse import DateRange, Parsed, best_match, norm, parse, parse_date
from app.db.models import Assignment, CalendarFeed, Course, Event, Exam, Topic
from app.llm.client import LLMClient
from app.llm.types import CallContext, LLMUnavailable
from app.orchestrator import actions
from app.orchestrator.events import emit

HELP = ["make me a 1h exam on entropy", "what did we cover last week in Fluids?", "move my Thermo exam to the 15th"]


class IntentGuess(BaseModel):
    """Closed-form output for the LLM fallback. No free-form structure is accepted."""

    intent: Literal["generate_exam", "ask_course", "change_exam_date", "open", "status", "unknown"]
    course: str | None = Field(default=None, max_length=120, description="course or exam name as written")
    topic: str | None = Field(default=None, max_length=120)
    date: str | None = Field(default=None, description="ISO date YYYY-MM-DD if the user gave one")
    duration_minutes: int | None = Field(default=None, ge=5, le=300)


class CommandResult(BaseModel):
    intent: str
    method: Literal["rules", "llm", "none"]
    outcome: Literal["job", "proposal", "navigate", "needs", "help", "info"]
    message: str
    job_id: str | None = None
    card_id: str | None = None
    route: str | None = None
    needs: str | None = None
    choices: list[dict[str, str]] = Field(default_factory=list)
    parsed: dict[str, Any] = Field(default_factory=dict)


def _courses(db: Session) -> list[Course]:
    return list(db.scalars(select(Course).order_by(Course.created_at)))


def _resolve_course(db: Session, text: str, topic: str | None) -> tuple[Course | None, list[Course]]:
    courses = _courses(db)
    if not courses:
        return None, []
    cid, ties = best_match(text, [(c.id, c.name) for c in courses])
    if cid:
        return next(c for c in courses if c.id == cid), []
    if ties:
        return None, [c for c in courses if c.id in ties]
    if topic:  # "exam on entropy" → the course that has a topic called like that
        topics = list(db.scalars(select(Topic)))
        tid, _ = best_match(topic, [(t.id, t.title) for t in topics])
        if tid:
            course_id = next(t.course_id for t in topics if t.id == tid)
            return next(c for c in courses if c.id == course_id), []
    if len(courses) == 1:
        return courses[0], []
    return None, courses


async def _llm_guess(llm: LLMClient, ctx: CallContext, text: str, courses: list[Course], today: date) -> IntentGuess | None:
    listing = ", ".join(c.name for c in courses) or "(none)"
    try:
        guess, _ = await llm.structured("jev_classification", [
            {"role": "system", "content": "You route a student's request to one of a few fixed intents. "
                                          "Answer only the closed question."},
            {"role": "user", "content": f"Today is {today.isoformat()}. The student's courses: {listing}.\n"
                                        f"Request: {text!r}\n"
                                        "Intents: generate_exam (make a practice exam), ask_course (a question about "
                                        "course content or what was covered), change_exam_date (move an exam to "
                                        "another date), open (navigate somewhere), unknown."},
        ], IntentGuess, ctx=ctx, reason="command bar: no rule matched (JEV)")
    except LLMUnavailable:
        return None
    return guess


async def run_command(db: Session, llm: LLMClient, user_id: str, text: str, today: date,
                      now: datetime) -> CommandResult:
    parsed = parse(text, today)
    method: Literal["rules", "llm", "none"] = "rules"
    if parsed.intent == "unknown":
        db.commit()  # the LLM call logs through its own session
        guess = await _llm_guess(llm, CallContext(user_id=user_id), text, _courses(db), today)
        method = "llm" if guess else "none"
        if guess and guess.intent != "unknown":
            parsed = Parsed(intent=guess.intent, text=text, topic=guess.topic, duration_minutes=guess.duration_minutes,
                            date=_iso(guess.date) or parse_date(norm(text), today),
                            date_range=parsed.date_range)
            if guess.course:
                parsed.text = f"{text} {guess.course}"
    result = _dispatch(db, parsed, today)
    result.method = method
    result.parsed = {"intent": parsed.intent, "date": parsed.date.isoformat() if parsed.date else None,
                     "duration_minutes": parsed.duration_minutes, "topic": parsed.topic,
                     "range": parsed.date_range.label if parsed.date_range else None}
    db.add(Event(type="command", source="manual",
                 payload={"text": text, "intent": result.intent, "method": method, "outcome": result.outcome,
                          "job_id": result.job_id, "card_id": result.card_id}))
    return result


def _iso(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _choices(courses: list[Course]) -> list[dict[str, str]]:
    return [{"id": c.id, "label": c.name} for c in courses]


def _status(db: Session, today: date) -> str:
    """What Novi is connected to and what it does with it, straight from the database."""
    feeds = list(db.scalars(select(CalendarFeed).order_by(CalendarFeed.created_at)))
    upcoming = list(db.scalars(select(Assignment).where(Assignment.done.is_(False), Assignment.due_date >= today)))
    if not feeds:
        return ("No calendar is connected yet. Paste your Atenea calendar link in Schedule → Connected calendars "
                "and I'll turn its deadlines into cards, re-checking every day.")
    parts = []
    for f in feeds:
        st = f.stats or {}
        when = f.last_synced_at.strftime("%d %b %H:%M") + " UTC" if f.last_synced_at else "not yet"
        line = f"Yes — {f.label} is connected (last checked {when})."
        if f.last_error:
            line += f" The last check failed: {f.last_error}"
        else:
            line += (f" Last check: {st.get('new', 0)} new, {st.get('updated', 0)} updated"
                     + (f", {st['unmatched']} event(s) not from your courses (e.g. {st['unmatched_examples'][0]})"
                        if st.get("unmatched") and st.get("unmatched_examples") else "") + ".")
        parts.append(line)
    parts.append(f"You have {len(upcoming)} open deadline(s) from it. I re-check every day and turn new deadlines "
                 "from your subjects into cards; exam events become exams with Exam Pack reminders.")
    return " ".join(parts)


def _dispatch(db: Session, p: Parsed, today: date) -> CommandResult:
    if p.intent == "generate_exam":
        course, options = _resolve_course(db, p.text, p.topic)
        if course is None:
            return CommandResult(intent=p.intent, method="rules", outcome="needs", needs="course",
                                 message="Which course should the exam be on?", choices=_choices(options))
        job = emit(db, "exam_requested", {"course_id": course.id, "focus": p.topic, "duration_minutes": p.duration_minutes,
                                          "n_exams": 1}, source="manual")
        what = f"{f'{p.duration_minutes}-min ' if p.duration_minutes else ''}{course.name} exam"
        return CommandResult(intent=p.intent, method="rules", outcome="job", job_id=job.id,
                             message=f"Building a {what}{f' on {p.topic}' if p.topic else ''} from your notes…")
    if p.intent == "ask_course":
        course, _ = _resolve_course(db, p.text, None)
        # A question may be about all courses: only use the course when the text names one.
        named = course if course is not None and best_match(p.text, [(course.id, course.name)])[0] else None
        rng = p.date_range or DateRange()
        job = emit(db, "question_asked", {"question": p.text, "course_id": named.id if named else None,
                                          "since": rng.since.isoformat() if rng.since else None,
                                          "until": rng.until.isoformat() if rng.until else None}, source="manual")
        return CommandResult(intent=p.intent, method="rules", outcome="job", job_id=job.id,
                             message=f"Looking through your {named.name + ' ' if named else ''}notes…")
    if p.intent == "change_exam_date":
        exams = list(db.scalars(select(Exam).order_by(Exam.exam_date)))
        courses = {c.id: c for c in _courses(db)}
        if not exams:
            return CommandResult(intent=p.intent, method="rules", outcome="help",
                                 message="You don't have any exams yet. Add one from a course or the Exam prep page.")
        eid, ties = best_match(p.text, [(e.id, f"{e.title} {courses[e.course_id].name}") for e in exams])
        if eid is None and len(exams) == 1:
            eid = exams[0].id
        if eid is None:
            opts = [e for e in exams if not ties or e.id in ties]
            return CommandResult(intent=p.intent, method="rules", outcome="needs", needs="exam",
                                 message="Which exam do you want to move?",
                                 choices=[{"id": e.id, "label": f"{e.title} ({e.exam_date:%d %b})"} for e in opts])
        exam = next(e for e in exams if e.id == eid)
        if p.date is None:
            return CommandResult(intent=p.intent, method="rules", outcome="needs", needs="date",
                                 message=f"To which date should I move {exam.title}?",
                                 choices=[{"id": exam.id, "label": exam.title}])
        if p.date == exam.exam_date:
            return CommandResult(intent=p.intent, method="rules", outcome="help",
                                 message=f"{exam.title} is already on {exam.exam_date:%d %b}.")
        _, card = actions.propose_exam_date(db, exam, courses[exam.course_id], p.date, p.text)
        return CommandResult(intent=p.intent, method="rules", outcome="proposal", card_id=card.id,
                             message=f"Move {exam.title} to {p.date:%A %d %b}? Approve it in the card.")
    if p.intent == "status":
        return CommandResult(intent=p.intent, method="rules", outcome="info", message=_status(db, today),
                             route="/schedule")
    if p.intent == "open":
        route = p.route
        if route is None:
            course, _ = _resolve_course(db, p.text, None)
            if course and best_match(p.text, [(course.id, course.name)])[0]:
                route = f"/subjects/{course.id}"
        if route:
            return CommandResult(intent=p.intent, method="rules", outcome="navigate", route=route, message="Opening…")
    return CommandResult(intent="unknown", method="rules", outcome="help",
                         message="I can make practice exams, answer questions about your courses, and move exam "
                                 "dates. Try: " + " · ".join(HELP))
