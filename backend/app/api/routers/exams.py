from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, get_or_404
from app.api.schemas import (
    AttemptOut,
    AttemptSubmitIn,
    ExamPackDetailOut,
    ExamPackOut,
    GuideSectionOut,
    JobOut,
    MockExamOut,
    QuestionOut,
)
from app.db.base import utcnow
from app.db.models import (
    Course,
    Exam,
    ExamAttempt,
    ExamPack,
    ExamQuestion,
    MockExam,
    NoteSection,
    StudyGuideSection,
    Topic,
)
from app.orchestrator.events import emit

router = APIRouter(tags=["exam packs"])


@router.get("/packs", response_model=list[ExamPackOut])
def list_packs(db: DB, exam_id: str | None = None, course_id: str | None = None) -> list[ExamPack]:
    q = select(ExamPack).order_by(ExamPack.created_at.desc())
    if exam_id:
        q = q.where(ExamPack.exam_id == exam_id)
    if course_id:
        q = q.where(ExamPack.course_id == course_id)
    return list(db.scalars(q))


def _questions(db: DB, mock_id: str, reveal: bool) -> list[QuestionOut]:
    rows = db.scalars(select(ExamQuestion).where(ExamQuestion.mock_exam_id == mock_id, ExamQuestion.state != "replaced")
                      .order_by(ExamQuestion.position))
    out = []
    for q in rows:
        item = QuestionOut.model_validate(q)
        if not reveal:
            item = item.model_copy(update={"solution_md": None, "rubric": None, "verification": None})
        else:
            item = item.model_copy(update={"solution_md": q.solution_md, "rubric": q.rubric,
                                           "verification": q.verification})
        out.append(item)
    return out


@router.get("/packs/{pack_id}", response_model=ExamPackDetailOut)
def get_pack(pack_id: str, db: DB, reveal: bool = False) -> ExamPackDetailOut:
    pack = get_or_404(db, ExamPack, pack_id)
    guide = list(db.scalars(select(StudyGuideSection).where(StudyGuideSection.pack_id == pack.id)
                            .order_by(StudyGuideSection.position)))
    mocks = list(db.scalars(select(MockExam).where(MockExam.pack_id == pack.id).order_by(MockExam.number)))
    mock_out = [MockExamOut.model_validate(m).model_copy(update={"questions": _questions(db, m.id, reveal)})
                for m in mocks]
    cited = {sid for g in guide for sid in g.cited_section_ids} | \
            {sid for m in mock_out for q in m.questions for sid in q.cited_section_ids}
    citations: dict[str, dict[str, str]] = {}
    for sid in cited:
        s = db.get(NoteSection, sid)
        if s is None:
            continue
        t = db.get(Topic, s.topic_id)
        citations[sid] = {"topic_id": s.topic_id, "topic_title": t.title if t else "", "heading": s.heading,
                          "course_id": s.course_id}
    return ExamPackDetailOut.model_validate({
        **ExamPackOut.model_validate(pack).model_dump(),
        "study_guide": [GuideSectionOut.model_validate(g) for g in guide],
        "mock_exams": mock_out, "citations": citations})


@router.post("/exams/{exam_id}/build-pack", response_model=JobOut, status_code=202)
def build_pack(exam_id: str, db: DB) -> object:
    """Manual trigger: emits the same `exam_approaching` event the scheduler emits at T-14/7/3."""
    get_or_404(db, Exam, exam_id)
    return emit(db, "exam_approaching", {"exam_id": exam_id}, source="manual")


@router.post("/courses/{course_id}/practice-exam", response_model=JobOut, status_code=202)
def practice_exam(course_id: str, db: DB) -> object:
    """On-demand exam for a subject, at any time."""
    get_or_404(db, Course, course_id)
    return emit(db, "exam_requested", {"course_id": course_id}, source="manual")


@router.get("/mock-exams/{mock_id}", response_model=MockExamOut)
def get_mock(mock_id: str, db: DB, reveal: bool = False) -> MockExamOut:
    m = get_or_404(db, MockExam, mock_id)
    return MockExamOut.model_validate(m).model_copy(update={"questions": _questions(db, m.id, reveal)})


@router.post("/mock-exams/{mock_id}/attempts", response_model=AttemptOut, status_code=201)
def start_attempt(mock_id: str, db: DB) -> ExamAttempt:
    get_or_404(db, MockExam, mock_id)
    a = ExamAttempt(mock_exam_id=mock_id)
    db.add(a)
    db.flush()
    return a


@router.get("/mock-exams/{mock_id}/attempts", response_model=list[AttemptOut])
def list_attempts(mock_id: str, db: DB) -> list[ExamAttempt]:
    get_or_404(db, MockExam, mock_id)
    return list(db.scalars(select(ExamAttempt).where(ExamAttempt.mock_exam_id == mock_id)
                           .order_by(ExamAttempt.started_at.desc())))


@router.put("/attempts/{attempt_id}", response_model=AttemptOut)
def save_attempt(attempt_id: str, body: AttemptSubmitIn, db: DB) -> ExamAttempt:
    a = get_or_404(db, ExamAttempt, attempt_id)
    if a.submitted_at and body.answers and body.answers != a.answers:
        raise HTTPException(409, "Answers are locked after submission")
    a.answers = body.answers or a.answers
    a.self_scores = body.self_scores or a.self_scores
    if body.submit and not a.submitted_at:
        a.submitted_at = utcnow()
    return a
