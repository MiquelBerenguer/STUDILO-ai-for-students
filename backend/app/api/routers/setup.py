"""Onboarding data: profile/semester, subjects, weekly schedule, exams, assignments."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_or_404
from app.api.schemas import (
    AssignmentIn,
    AssignmentOut,
    CourseIn,
    CourseOut,
    ExamIn,
    ExamOut,
    ExamPatch,
    MeOut,
    ProfileIn,
    SlotIn,
    SlotOut,
)
from app.db.engine import system_session_ctx
from app.db.models import Assignment, ClassSlot, Course, CourseMemory, Exam, User
from app.orchestrator import cards
from app.orchestrator.state_machines import JOURNEY, transition

router = APIRouter(tags=["setup"])


# ---------------------------------------------------------------- profile
@router.put("/me/profile", response_model=MeOut)
def update_profile(body: ProfileIn, user: CurrentUser) -> User:
    with system_session_ctx() as db:  # users table is identity, not UserOwned; we only touch our own row
        row = db.get(User, user.id)
        assert row is not None
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(row, field, value)
        if row.semester_start and row.semester_end and row.semester_end <= row.semester_start:
            raise HTTPException(422, "semester_end must be after semester_start")
        return row


@router.post("/me/complete-onboarding", response_model=MeOut)
def complete_onboarding(user: CurrentUser, db: DB) -> User:
    n_courses = db.scalar(select(func.count()).select_from(Course)) or 0
    n_slots = db.scalar(select(func.count()).select_from(ClassSlot)) or 0
    with system_session_ctx() as sdb:
        row = sdb.get(User, user.id)
        assert row is not None
        missing = [label for label, ok in (
            ("at least one subject", n_courses > 0),
            ("a weekly schedule", n_slots > 0),
            ("semester dates", bool(row.semester_start and row.semester_end)),
        ) if not ok]
        if missing:
            raise HTTPException(status.HTTP_409_CONFLICT, "Onboarding incomplete: add " + ", ".join(missing))
        if row.journey_state != "active":
            transition(JOURNEY, _JourneyView(row), "active")
        return row


class _JourneyView:
    """Adapter so the generic `transition()` can drive User.journey_state."""

    def __init__(self, user: User):
        self._u = user

    @property
    def state(self) -> str:
        return self._u.journey_state

    @state.setter
    def state(self, v: str) -> None:
        self._u.journey_state = v


# ---------------------------------------------------------------- courses
@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: DB) -> list[Course]:
    return list(db.scalars(select(Course).order_by(Course.created_at)))


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseIn, db: DB) -> Course:
    course = Course(**body.model_dump())
    db.add(course)
    db.flush()
    db.add(CourseMemory(course_id=course.id))
    return course


@router.get("/courses/{course_id}", response_model=CourseOut)
def get_course(course_id: str, db: DB) -> Course:
    return get_or_404(db, Course, course_id)


@router.put("/courses/{course_id}", response_model=CourseOut)
def update_course(course_id: str, body: CourseIn, db: DB) -> Course:
    course = get_or_404(db, Course, course_id)
    for k, v in body.model_dump().items():
        setattr(course, k, v)
    return course


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: str, db: DB) -> None:
    db.delete(get_or_404(db, Course, course_id))


# ---------------------------------------------------------------- schedule
@router.get("/slots", response_model=list[SlotOut])
def list_slots(db: DB) -> list[ClassSlot]:
    return list(db.scalars(select(ClassSlot).order_by(ClassSlot.weekday, ClassSlot.start_time)))


@router.post("/courses/{course_id}/slots", response_model=SlotOut, status_code=201)
def create_slot(course_id: str, body: SlotIn, db: DB) -> ClassSlot:
    get_or_404(db, Course, course_id)
    slot = ClassSlot(course_id=course_id, **body.model_dump())
    db.add(slot)
    db.flush()
    return slot


@router.delete("/slots/{slot_id}", status_code=204)
def delete_slot(slot_id: str, db: DB) -> None:
    db.delete(get_or_404(db, ClassSlot, slot_id))


# ---------------------------------------------------------------- exams
@router.get("/exams", response_model=list[ExamOut])
def list_exams(db: DB) -> list[Exam]:
    return list(db.scalars(select(Exam).order_by(Exam.exam_date)))


@router.post("/exams", response_model=ExamOut, status_code=201)
def create_exam(body: ExamIn, db: DB) -> Exam:
    course = get_or_404(db, Course, body.course_id)
    return cards.create_exam_with_followups(db, course, body.exam_date, body.title, body.scope_note)


@router.patch("/exams/{exam_id}", response_model=ExamOut)
def update_exam(exam_id: str, body: ExamPatch, db: DB) -> Exam:
    exam = get_or_404(db, Exam, exam_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(exam, k, v)
    return exam


@router.delete("/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: str, db: DB) -> None:
    db.delete(get_or_404(db, Exam, exam_id))


# ---------------------------------------------------------------- assignments
@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(db: DB) -> list[Assignment]:
    return list(db.scalars(select(Assignment).order_by(Assignment.due_date)))


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(body: AssignmentIn, db: DB) -> Assignment:
    get_or_404(db, Course, body.course_id)
    a = Assignment(**body.model_dump())
    db.add(a)
    db.flush()
    return a


@router.patch("/assignments/{assignment_id}", response_model=AssignmentOut)
def toggle_assignment(assignment_id: str, done: bool, db: DB) -> Assignment:
    a = get_or_404(db, Assignment, assignment_id)
    a.done = done
    return a


@router.delete("/assignments/{assignment_id}", status_code=204)
def delete_assignment(assignment_id: str, db: DB) -> None:
    db.delete(get_or_404(db, Assignment, assignment_id))
