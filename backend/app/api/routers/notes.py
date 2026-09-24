from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_or_404
from app.api.schemas import (
    ClassSessionOut,
    CourseMemoryOut,
    DependencyOut,
    OpenQuestionOut,
    SearchHit,
    SectionOut,
    SourceRef,
    TopicNoteOut,
    TopicOut,
)
from app.db.models import ClassSession, Course, NoteSection, OpenQuestion, Topic, TopicDependency
from app.tools import store
from app.tools.memory import memory_row

router = APIRouter(tags=["notes"])


@router.get("/courses/{course_id}/topics", response_model=list[TopicOut])
def list_topics(course_id: str, db: DB) -> list[TopicOut]:
    get_or_404(db, Course, course_id)
    counts = dict(db.execute(select(NoteSection.topic_id, func.count()).where(NoteSection.course_id == course_id)
                             .group_by(NoteSection.topic_id)).all())
    return [TopicOut.model_validate(t).model_copy(update={"section_count": counts.get(t.id, 0)})
            for t in db.scalars(select(Topic).where(Topic.course_id == course_id).order_by(Topic.position))]


@router.get("/topics/{topic_id}/note", response_model=TopicNoteOut)
def topic_note(topic_id: str, db: DB) -> TopicNoteOut:
    topic = get_or_404(db, Topic, topic_id)
    sections = store.topic_sections(db, topic.id)
    sources = store.section_sources(db, [s.id for s in sections])
    return TopicNoteOut(
        topic=TopicOut.model_validate(topic).model_copy(update={"section_count": len(sections)}),
        sections=[SectionOut.model_validate(s).model_copy(update={"sources": [
            SourceRef(upload_id=u.id, filename=u.filename, created_at=u.created_at) for u in sources.get(s.id, [])]})
            for s in sections])


@router.get("/notes/search", response_model=list[SearchHit])
async def search(user: CurrentUser, db: DB, q: str = Query(min_length=2, max_length=300),
                 course_id: str | None = None) -> list[dict[str, object]]:
    if course_id:
        get_or_404(db, Course, course_id)
    return await store.search_notes(db, user.id, q, course_id=course_id, k=8)


@router.get("/courses/{course_id}/memory", response_model=CourseMemoryOut)
def course_memory(course_id: str, db: DB) -> CourseMemoryOut:
    get_or_404(db, Course, course_id)
    mem = memory_row(db, course_id)
    sessions = list(db.scalars(select(ClassSession).where(ClassSession.course_id == course_id)
                               .order_by(ClassSession.session_date.desc()).limit(100)))
    questions = list(db.scalars(select(OpenQuestion).where(OpenQuestion.course_id == course_id)
                                .order_by(OpenQuestion.created_at.desc())))
    deps = list(db.scalars(select(TopicDependency).where(TopicDependency.course_id == course_id)))
    return CourseMemoryOut(
        course_id=course_id, topics_per_week=mem.topics_per_week, syllabus_position=mem.syllabus_position,
        pace_note=mem.pace_note, sessions=[ClassSessionOut.model_validate(s) for s in sessions],
        open_questions=[OpenQuestionOut.model_validate(q) for q in questions],
        dependencies=[DependencyOut(topic_id=d.topic_id, depends_on_id=d.depends_on_id) for d in deps],
        missed_count=sum(1 for s in sessions if s.state == "missed"))


@router.post("/open-questions/{question_id}/resolve", response_model=OpenQuestionOut)
def resolve_question(question_id: str, db: DB) -> OpenQuestion:
    q = get_or_404(db, OpenQuestion, question_id)
    q.status = "resolved"
    return q
