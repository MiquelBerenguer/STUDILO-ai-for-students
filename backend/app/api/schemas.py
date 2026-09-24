"""HTTP request/response schemas (Pydantic v2)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MeOut(ORM):
    id: str
    email: str
    display_name: str
    journey_state: str
    timezone: str
    semester_start: date | None
    semester_end: date | None
    missed_after_hours: int


# ---- profile / onboarding
class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    timezone: str | None = None
    semester_start: date | None = None
    semester_end: date | None = None
    missed_after_hours: int | None = Field(default=None, ge=1, le=168)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone {v!r}") from exc
        return v

    @model_validator(mode="after")
    def _dates(self) -> ProfileIn:
        if self.semester_start and self.semester_end and self.semester_end <= self.semester_start:
            raise ValueError("semester_end must be after semester_start")
        return self


# ---- courses & schedule
class CourseIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    syllabus: str = Field(default="", max_length=20000)


class CourseOut(ORM):
    id: str
    name: str
    color: str
    syllabus: str


class SlotIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: str
    end_time: str
    location: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _times(self) -> SlotIn:
        for t in (self.start_time, self.end_time):
            if not _HHMM.match(t):
                raise ValueError(f"Time {t!r} must be HH:MM")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class SlotOut(ORM):
    id: str
    course_id: str
    weekday: int
    start_time: str
    end_time: str
    location: str


class ExamIn(BaseModel):
    course_id: str
    title: str = Field(min_length=1, max_length=160)
    exam_date: date
    scope_note: str = Field(default="", max_length=5000)


class ExamPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    exam_date: date | None = None
    scope_note: str | None = Field(default=None, max_length=5000)


class ExamOut(ORM):
    id: str
    course_id: str
    title: str
    exam_date: date
    scope_note: str


class AssignmentIn(BaseModel):
    course_id: str
    title: str = Field(min_length=1, max_length=200)
    due_date: date
    done: bool = False


class AssignmentOut(ORM):
    id: str
    course_id: str
    title: str
    due_date: date
    done: bool


# ---- sessions / uploads
class ClassSessionOut(ORM):
    id: str
    course_id: str
    slot_id: str | None
    session_date: date
    starts_at: datetime | None
    ends_at: datetime | None
    state: str
    summary_md: str
    topic_ids: list[str]
    missed_reason: str


class UploadOut(ORM):
    id: str
    course_id: str
    class_session_id: str | None
    kind: str
    filename: str
    detected_type: str
    size_bytes: int
    state: str
    status_message: str
    error: str
    topic_id: str | None
    job_id: str | None
    created_at: datetime
    updated_at: datetime


class IngestionLogOut(ORM):
    id: str
    page: int | None
    step: str
    path_taken: str
    reason: str
    legibility_score: float | None
    ocr_confidence: float | None
    scores: dict[str, Any]
    model_used: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    created_at: datetime


class UploadDetailOut(UploadOut):
    extracted_md: str
    log: list[IngestionLogOut]


# ---- notes
class TopicOut(ORM):
    id: str
    course_id: str
    parent_id: str | None
    title: str
    summary: str
    position: int
    section_count: int = 0


class SourceRef(BaseModel):
    upload_id: str
    filename: str
    created_at: datetime


class SectionOut(ORM):
    id: str
    topic_id: str
    position: int
    heading: str
    content_md: str
    version: int
    updated_at: datetime
    sources: list[SourceRef] = []


class TopicNoteOut(BaseModel):
    topic: TopicOut
    sections: list[SectionOut]


class SearchHit(BaseModel):
    section_id: str
    topic_id: str
    topic_title: str
    heading: str
    snippet: str
    score: float


# ---- memory
class OpenQuestionOut(ORM):
    id: str
    course_id: str
    topic_id: str | None
    text: str
    status: str
    created_at: datetime


class DependencyOut(BaseModel):
    topic_id: str
    depends_on_id: str


class CourseMemoryOut(BaseModel):
    course_id: str
    topics_per_week: float
    syllabus_position: str
    pace_note: str
    sessions: list[ClassSessionOut]
    open_questions: list[OpenQuestionOut]
    dependencies: list[DependencyOut]
    missed_count: int


# ---- exams
class RubricItem(BaseModel):
    criterion: str
    points: float


class QuestionOut(ORM):
    id: str
    position: int
    topic_id: str | None
    statement_md: str
    points: float
    cited_section_ids: list[str]
    state: str
    solution_md: str | None = None
    rubric: list[dict[str, Any]] | None = None
    verification: dict[str, Any] | None = None


class PracticeExamOut(ORM):
    id: str
    number: int
    title: str
    duration_minutes: int
    questions: list[QuestionOut] = []


class GuideSectionOut(ORM):
    id: str
    topic_id: str | None
    position: int
    heading: str
    content_md: str
    cited_section_ids: list[str]


class ExamPackOut(ORM):
    id: str
    course_id: str
    exam_id: str | None
    version: int
    trigger: str
    state: str
    error: str
    notes_cutoff: datetime | None
    built_at: datetime | None
    job_id: str | None
    created_at: datetime


class ExamPackDetailOut(ExamPackOut):
    study_guide: list[GuideSectionOut]
    practice_exams: list[PracticeExamOut]
    citations: dict[str, dict[str, str]]  # section_id -> {topic_title, heading, topic_id}


class AttemptOut(ORM):
    id: str
    practice_exam_id: str
    started_at: datetime
    submitted_at: datetime | None
    answers: dict[str, str]
    self_scores: dict[str, float]


class AttemptSubmitIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    self_scores: dict[str, float] = Field(default_factory=dict)
    submit: bool = True


# ---- orchestration / activity
class JobOut(ORM):
    id: str
    type: str
    state: str
    progress: str
    error: str
    attempts: int
    payload: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class NotificationOut(ORM):
    id: str
    kind: str
    title: str
    body: str
    link: str
    data: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class AgentRunOut(ORM):
    id: str
    agent: str
    mode: str
    prompt_version: str
    task: str
    job_id: str | None
    state: str
    goal: str
    output: str
    error: str
    steps: int
    llm_calls: int
    cost_usd: float
    created_at: datetime
    finished_at: datetime | None


class AgentStepOut(ORM):
    id: str
    idx: int
    kind: str
    name: str
    input: Any
    output: Any
    ok: bool
    latency_ms: int
    created_at: datetime


class LLMCallOut(ORM):
    id: str
    agent_run_id: str | None
    task: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    priced: bool
    latency_ms: int
    ok: bool
    error: str
    is_fallback: bool
    reason: str
    created_at: datetime


class EventIn(BaseModel):
    """Manual triggers from the UI: the same event types the scheduler emits."""

    type: Literal["class_ended", "exam_approaching", "exam_requested", "class_slot_passed_without_upload"]
    slot_id: str | None = None
    session_date: date | None = None
    exam_id: str | None = None
    course_id: str | None = None


class TickIn(BaseModel):
    now: datetime | None = None


# ---- settings
class ProviderStatus(BaseModel):
    name: str
    key_env: str | None
    configured: bool
    masked_key: str | None
    base_url: str
    used_by: list[str]


class TaskMappingIn(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=160)
    fallback: list[str] = Field(default_factory=list, max_length=4)
