"""ORM schema. Every user-owned row carries `user_id` (UserOwned mixin). Changes need an Alembic migration."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, UserOwned, UTCDateTime, utcnow


# --------------------------------------------------------------------------- identity
class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)  # None = guest
    password_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    journey_state: Mapped[str] = mapped_column(String(20), default="onboarding")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Madrid")
    semester_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    semester_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    missed_after_hours: Mapped[int] = mapped_column(Integer, default=12)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)  # feed "since you were away"

    @property
    def is_guest(self) -> bool:
        return self.email is None


class AuthSession(IdMixin, TimestampMixin, Base):
    """Login session. Not UserOwned on purpose: looked up by token hash before a user is known."""

    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())


# --------------------------------------------------------------------------- setup
class Course(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "courses"
    name: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(16), default="#6366f1")
    syllabus: Mapped[str] = mapped_column(Text, default="")
    professor: Mapped[str] = mapped_column(String(160), default="")
    slots: Mapped[list[ClassSlot]] = relationship(back_populates="course", cascade="all, delete-orphan")


class ClassSlot(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "class_slots"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" local time
    end_time: Mapped[str] = mapped_column(String(5))
    location: Mapped[str] = mapped_column(String(120), default="")
    course: Mapped[Course] = relationship(back_populates="slots")


class Exam(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "exams"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    exam_date: Mapped[date] = mapped_column(Date)
    scope_note: Mapped[str] = mapped_column(Text, default="")
    external_uid: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)  # iCal UID (feed sync)


class Assignment(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "assignments"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    external_uid: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)  # iCal UID (feed sync)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)  # exact time when the source has one


class CalendarFeed(IdMixin, TimestampMixin, UserOwned, Base):
    """A calendar the student connected (e.g. Atenea/Moodle export URL). The URL is a secret: stored encrypted."""

    __tablename__ = "calendar_feeds"
    url_enc: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(120), default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------- sessions & uploads
class ClassSession(IdMixin, TimestampMixin, UserOwned, Base):
    """One occurrence of a class (from a slot, or ad-hoc for uploads without a slot)."""

    __tablename__ = "class_sessions"
    __table_args__ = (UniqueConstraint("slot_id", "session_date", name="uq_class_sessions_slot_date"),)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    slot_id: Mapped[str | None] = mapped_column(ForeignKey("class_slots.id", ondelete="SET NULL"), nullable=True)
    session_date: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="scheduled")
    summary_md: Mapped[str] = mapped_column(Text, default="")
    topic_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    missed_reason: Mapped[str] = mapped_column(String(200), default="")


class Upload(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "uploads"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    class_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("class_sessions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), default="notes")  # notes | past_exam
    filename: Mapped[str] = mapped_column(String(255))
    detected_type: Mapped[str] = mapped_column(String(16), default="unknown")
    storage_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="received")
    status_message: Mapped[str] = mapped_column(String(300), default="Waiting to start")
    error: Mapped[str] = mapped_column(Text, default="")
    extracted_md: Mapped[str] = mapped_column(Text, default="")
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class IngestionLog(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "ingestion_log"
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step: Mapped[str] = mapped_column(String(32))  # detect | legibility | ocr | vision | subject | topic
    path_taken: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(300), default="")
    legibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_used: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- notes
class Topic(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "topics"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(160), nullable=True)


class TopicDependency(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "topic_dependencies"
    __table_args__ = (UniqueConstraint("topic_id", "depends_on_id", name="uq_topic_dependencies_pair"),)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    depends_on_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))


class NoteSection(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "note_sections"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    heading: Mapped[str] = mapped_column(String(200))
    content_md: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class SectionSource(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "section_sources"
    __table_args__ = (UniqueConstraint("section_id", "upload_id", name="uq_section_sources_pair"),)
    section_id: Mapped[str] = mapped_column(ForeignKey("note_sections.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)


class Chunk(TimestampMixin, UserOwned, Base):
    """Embeddable text chunk of a note section. Integer PK = rowid in the sqlite-vec table."""

    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[str] = mapped_column(ForeignKey("note_sections.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    embedding_dim: Mapped[int] = mapped_column(Integer)


# --------------------------------------------------------------------------- course memory
class CourseMemory(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "course_memory"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), unique=True)
    topics_per_week: Mapped[float] = mapped_column(Float, default=0.0)
    syllabus_position: Mapped[str] = mapped_column(Text, default="")
    pace_note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class OpenQuestion(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "open_questions"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open")
    source_upload_id: Mapped[str | None] = mapped_column(ForeignKey("uploads.id", ondelete="SET NULL"), nullable=True)


# --------------------------------------------------------------------------- orchestration
class Event(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "events"
    type: Mapped[str] = mapped_column(String(48), index=True)
    source: Mapped[str] = mapped_column(String(16), default="system")  # scheduler | manual | system
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Job(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "jobs"
    type: Mapped[str] = mapped_column(String(48), index=True)
    state: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    progress: Mapped[str] = mapped_column(String(300), default="")


class TriggerLog(IdMixin, TimestampMixin, UserOwned, Base):
    """Idempotency keys for automatic triggers (e.g. `exam_approaching:<exam>:T-7`)."""

    __tablename__ = "trigger_log"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_trigger_log_user_key"),)
    key: Mapped[str] = mapped_column(String(200))


class Notification(IdMixin, TimestampMixin, UserOwned, Base):
    """An action card in the Novi feed (UX.md §4). Created only by triggers and jobs."""

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),)
    kind: Mapped[str] = mapped_column(String(32))  # see app/orchestrator/cards.py CARD_KINDS
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(300), default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | done | dismissed
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action_id: Mapped[str | None] = mapped_column(ForeignKey("agent_actions.id", ondelete="SET NULL"), nullable=True)
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AgentAction(IdMixin, TimestampMixin, UserOwned, Base):
    """Something Novi did (applied, undoable) or wants to do (proposed, needs approval). UX.md §7."""

    __tablename__ = "agent_actions"
    kind: Mapped[str] = mapped_column(String(40))  # file_notes | build_pack | change_exam_date
    risk: Mapped[str] = mapped_column(String(8))  # low | high
    status: Mapped[str] = mapped_column(String(16), index=True)  # proposed | applied | rejected | undone
    title: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # what to apply (proposals)
    effects: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # snapshot needed to undo
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    upload_id: Mapped[str | None] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AgentRun(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "agent_runs"
    agent: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # llm | deterministic
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    task: Mapped[str] = mapped_column(String(32), default="")
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="running")
    goal: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AgentStep(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "agent_steps"
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))  # llm | tool | decision
    name: Mapped[str] = mapped_column(String(64))
    input: Mapped[Any] = mapped_column(JSON, default=dict)
    output: Mapped[Any] = mapped_column(JSON, default=dict)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class LLMCall(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "llm_calls"
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    task: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    priced: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(Text, default="")
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(300), default="")


# --------------------------------------------------------------------------- exam packs
class ExamPack(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "exam_packs"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    exam_id: Mapped[str | None] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    trigger: Mapped[str] = mapped_column(String(40), default="manual")
    state: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    notes_cutoff: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    built_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class StudyGuideSection(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "study_guide_sections"
    pack_id: Mapped[str] = mapped_column(ForeignKey("exam_packs.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    heading: Mapped[str] = mapped_column(String(200))
    content_md: Mapped[str] = mapped_column(Text)
    cited_section_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class PracticeExam(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "practice_exams"
    pack_id: Mapped[str] = mapped_column(ForeignKey("exam_packs.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)


class ExamQuestion(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "exam_questions"
    practice_exam_id: Mapped[str] = mapped_column(ForeignKey("practice_exams.id", ondelete="CASCADE"), index=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("exam_packs.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    statement_md: Mapped[str] = mapped_column(Text)
    solution_md: Mapped[str] = mapped_column(Text)
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    points: Mapped[float] = mapped_column(Float, default=10.0)
    cited_section_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(16), default="draft")  # draft | verified | rejected | replaced
    verification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ExamAttempt(IdMixin, TimestampMixin, UserOwned, Base):
    __tablename__ = "exam_attempts"
    practice_exam_id: Mapped[str] = mapped_column(ForeignKey("practice_exams.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    answers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    self_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
