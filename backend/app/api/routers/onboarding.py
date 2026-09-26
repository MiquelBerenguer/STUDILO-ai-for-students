"""Three-step onboarding (UX.md §8): drop timetable → confirm week → Novi feed."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.base import ToolContext
from app.api.deps import DB, CurrentUser
from app.api.schemas import CourseOut
from app.auth.ratelimit import RateLimiter
from app.command.parse import GROUP_SUFFIX, best_match, strip_group
from app.config.settings import get_settings
from app.db.base import utcnow
from app.db.engine import system_session_ctx
from app.db.models import ClassSlot, Course, User
from app.llm.client import get_llm
from app.onboarding.extract import ExtractionError, extract_timetable
from app.onboarding.timetable import ExamOut, Extraction, SlotOut, norm
from app.orchestrator import cards
from app.orchestrator.state_machines import JOURNEY, transition

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
extract_limiter = RateLimiter(limit=30, window_s=3600)  # extractions per user per hour (each may call a model)

# The reference design's course accents, then a few more distinct ones.
PALETTE = ["#6558e8", "#4a78cf", "#d57d37", "#39a978", "#c2528b", "#2f9fb4", "#8a6d3b", "#7b61c9"]


class ConfirmIn(BaseModel):
    slots: list[SlotOut] = Field(min_length=1, max_length=80)
    exams: list[ExamOut] = Field(default_factory=list, max_length=40)


class ConfirmOut(BaseModel):
    courses: list[CourseOut]
    slots_created: int
    exams_created: int
    journey_state: str


@router.post("/extract", response_model=Extraction)
async def extract(user: CurrentUser, db: DB, file: UploadFile | None = File(default=None),
                  text: str | None = Form(default=None, max_length=20000),
                  url: str | None = Form(default=None, max_length=2000)) -> Extraction:
    """Step 1: read a timetable from a screenshot/photo/PDF/.ics file, an .ics link or pasted text."""
    if not extract_limiter.allow(user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in a while.")
    data = None
    if file is not None:
        data = await file.read(get_settings().MAX_UPLOAD_MB * 1024 * 1024 + 1)
        if len(data) > get_settings().MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"The file is larger than {get_settings().MAX_UPLOAD_MB} MB")
    with system_session_ctx() as sdb:
        tz = sdb.get(User, user.id).timezone  # type: ignore[union-attr]
    ctx = ToolContext(user_id=user.id, db=db, llm=get_llm(), now=utcnow())
    try:
        return await extract_timetable(ctx, data=data, text=text, url=url, tz=tz)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/confirm", response_model=ConfirmOut)
def confirm(body: ConfirmIn, user: CurrentUser, db: DB) -> ConfirmOut:
    """Step 2: one tap. Creates subjects + weekly slots (+ exam dates found in a calendar) and starts following."""
    courses = list(db.scalars(select(Course).order_by(Course.created_at)))
    by_name = {norm(c.name): c for c in courses}
    touched: dict[str, Course] = {}
    created_slots = 0
    for s in body.slots:
        # "ELECTRI(G)" and "ELECTRI(P)" are the theory and lab groups of one subject: one course, two slots.
        marker = GROUP_SUFFIX.search(s.subject)
        name = strip_group(s.subject) or s.subject
        room = f"({marker.group(1).upper()}) {s.room}".strip() if marker else s.room
        key = norm(name)
        course = by_name.get(key)
        if course is None:
            course = Course(name=name.strip()[:120], color=PALETTE[len(by_name) % len(PALETTE)],
                            professor=s.professor)
            db.add(course)
            db.flush()
            by_name[key] = course
        elif s.professor and not course.professor:
            course.professor = s.professor
        touched[course.id] = course
        exists = db.scalar(select(ClassSlot.id).where(ClassSlot.course_id == course.id, ClassSlot.weekday == s.weekday,
                                                      ClassSlot.start_time == s.start, ClassSlot.end_time == s.end))
        if not exists:
            db.add(ClassSlot(course_id=course.id, weekday=s.weekday, start_time=s.start, end_time=s.end,
                             location=room))
            created_slots += 1
    exams = 0
    all_courses = list(by_name.values())
    for e in body.exams:
        cid, _ = best_match(e.subject or e.title, [(c.id, c.name) for c in all_courses])
        if cid:
            cards.create_exam_with_followups(db, next(c for c in all_courses if c.id == cid), e.date, e.title)
            exams += 1
    db.flush()
    choices = [{"id": c.id, "name": c.name} for c in touched.values()]
    cards.create_card(
        db, "backfill_notes", "Semester already started? Drop the notes you already have",
        body="Photos, PDFs or typed notes from earlier classes. I'll file them into topics and catch up your "
             "course memory.",
        actions=[cards.action("drop_notes", "Drop notes", "upload", primary=True,
                              params={"kind": "notes"}, course_choices=choices), cards.DISMISS],
        dedupe_key="backfill_notes", priority=48)
    cards.create_card(
        db, "connect_calendar", "Want your Atenea deadlines too?",
        body="In Atenea open Calendar → Export calendar → All courses → Get calendar URL, and paste it here. "
             "I'll re-check it every day and turn deadlines into cards. No password needed.",
        actions=[cards.action("connect_calendar", "Connect", "input", primary=True,
                              placeholder="https://atenea.upc.edu/calendar/export_execute.php?…", input_type="url"),
                 cards.action("dismiss", "Not now")],
        dedupe_key="connect_calendar", priority=47)
    db.commit()  # release the SQLite write lock before the user row is updated in its own session
    with system_session_ctx() as sdb:
        row = sdb.get(User, user.id)
        assert row is not None
        if row.journey_state == "onboarding":
            transition(JOURNEY, row, "active", attr="journey_state")
        state = row.journey_state
    return ConfirmOut(courses=[CourseOut.model_validate(c) for c in touched.values()], slots_created=created_slots,
                      exams_created=exams, journey_state=state)
