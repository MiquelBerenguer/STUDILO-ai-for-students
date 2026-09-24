"""Exam agent tools. Questions must cite the student's note sections and pass verification."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.base import Tool, ToolContext, ToolError, load_prompt
from app.db.base import utcnow
from app.db.models import (
    ClassSession,
    Course,
    Exam,
    ExamPack,
    ExamQuestion,
    NoteSection,
    OpenQuestion,
    PracticeExam,
    StudyGuideSection,
    Topic,
    Upload,
)
from app.llm.types import LLMUnavailable
from app.orchestrator.state_machines import EXAM_PACK, transition
from app.tools import store
from app.tools.memory import memory_row
from app.tools.notes import SearchArgs


def _pack(ctx: ToolContext) -> ExamPack:
    return store.must_get(ctx.db, ExamPack, ctx.state["pack_id"], "exam pack")


def _check_sections(ctx: ToolContext, ids: list[str]) -> list[NoteSection]:
    if not ids:
        raise ToolError("cite at least one note section (section_id from search_notes / get_exam_scope)")
    out = []
    for sid in ids:
        s = ctx.db.get(NoteSection, sid)
        if s is None or s.course_id != ctx.state["course_id"]:
            raise ToolError(f"section {sid!r} is not one of this subject's note sections")
        out.append(s)
    return out


class NoArgs(BaseModel):
    pass


class ReadSectionsArgs(BaseModel):
    section_ids: list[str] = Field(min_length=1, max_length=12)


class GuideArgs(BaseModel):
    heading: str = Field(min_length=2, max_length=200)
    content_md: str = Field(min_length=20, max_length=12000)
    cited_section_ids: list[str] = Field(min_length=1)
    topic_id: str | None = None


class RubricItem(BaseModel):
    criterion: str = Field(min_length=2, max_length=300)
    points: float = Field(gt=0, le=100)


class DraftArgs(BaseModel):
    practice_exam_number: int = Field(ge=1, le=10)
    topic_id: str | None = None
    statement_md: str = Field(min_length=20, max_length=8000, description="all data needed to solve it, with units")
    solution_md: str = Field(min_length=20, max_length=12000, description="complete worked solution")
    rubric: list[RubricItem] = Field(min_length=1, max_length=10)
    points: float = Field(gt=0, le=100)
    cited_section_ids: list[str] = Field(min_length=1)
    replaces_question_id: str | None = None


class QuestionArg(BaseModel):
    question_id: str


class PracticeMeta(BaseModel):
    number: int = Field(ge=1, le=10)
    title: str = Field(min_length=2, max_length=200)
    duration_minutes: int = Field(ge=10, le=300)


class SaveArgs(BaseModel):
    practice_exams: list[PracticeMeta] = Field(min_length=1)


class Verification(BaseModel):
    solvable_with_given_data: bool
    units_consistent: bool
    answer_supported_by_notes: bool
    issues: list[str] = Field(default_factory=list, max_length=6)


def get_exam_scope_tool(ctx: ToolContext, _a: NoArgs) -> dict[str, object]:
    pack = _pack(ctx)
    course = store.must_get(ctx.db, Course, pack.course_id, "course")
    exam = ctx.db.get(Exam, pack.exam_id) if pack.exam_id else None
    topics = list(ctx.db.scalars(select(Topic).where(Topic.course_id == course.id).order_by(Topic.position)))
    prev = ctx.db.scalar(select(ExamPack).where(ExamPack.course_id == course.id, ExamPack.exam_id == pack.exam_id,
                                                ExamPack.state == "ready").order_by(ExamPack.version.desc()))
    mem = memory_row(ctx.db, course.id)
    missed = list(ctx.db.scalars(select(ClassSession).where(ClassSession.course_id == course.id,
                                                           ClassSession.state == "missed")))
    open_q = list(ctx.db.scalars(select(OpenQuestion).where(OpenQuestion.course_id == course.id,
                                                            OpenQuestion.status == "open")))
    topic_rows = []
    new_since = []
    for t in topics:
        secs = store.topic_sections(ctx.db, t.id)
        topic_rows.append({"topic_id": t.id, "title": t.title, "summary": t.summary,
                           "sections": [{"section_id": s.id, "heading": s.heading} for s in secs]})
        if prev and prev.notes_cutoff:
            new_since += [s.id for s in secs if s.updated_at > prev.notes_cutoff]
    return {
        "course": course.name, "syllabus": course.syllabus[:2000],
        "exam": None if exam is None else {"title": exam.title, "date": exam.exam_date.isoformat(),
                                           "days_left": (exam.exam_date - ctx.now.date()).days,
                                           "scope_note": exam.scope_note},
        "requirements": {"practice_exams": ctx.state["n_exams"], "questions_per_exam": ctx.state["n_questions"]},
        "topics": topic_rows,
        "course_memory": {"pace": mem.syllabus_position, "topics_per_week": mem.topics_per_week,
                          "missed_sessions": [s.session_date.isoformat() for s in missed],
                          "open_questions": [q.text for q in open_q]},
        "previous_build": None if prev is None else {"version": prev.version,
                                                     "sections_new_or_changed_since": new_since},
    }


async def search_notes_tool(ctx: ToolContext, a: SearchArgs) -> list[dict[str, object]]:
    ctx.db.commit()
    return await store.search_notes(ctx.db, ctx.user_id, a.query, course_id=ctx.state["course_id"],
                                    topic_id=a.topic_id, k=a.k)


def read_sections_tool(ctx: ToolContext, a: ReadSectionsArgs) -> list[dict[str, object]]:
    return [{"section_id": s.id, "topic_id": s.topic_id, "heading": s.heading, "content_md": s.content_md[:5000]}
            for s in _check_sections(ctx, a.section_ids)]


def get_past_exams_tool(ctx: ToolContext, _a: NoArgs) -> dict[str, object]:
    rows = list(ctx.db.scalars(select(Upload).where(Upload.course_id == ctx.state["course_id"],
                                                    Upload.kind == "past_exam", Upload.state == "done")
                               .order_by(Upload.created_at.desc()).limit(3)))
    if not rows:
        return {"past_exams": [], "note": "No past exams uploaded: use a standard university engineering exam style."}
    return {"past_exams": [{"filename": u.filename, "text": u.extracted_md[:6000]} for u in rows]}


def add_study_guide_section_tool(ctx: ToolContext, a: GuideArgs) -> dict[str, object]:
    _check_sections(ctx, a.cited_section_ids)
    if a.topic_id:
        t = store.must_get(ctx.db, Topic, a.topic_id, "topic")
        if t.course_id != ctx.state["course_id"]:
            raise ToolError("topic belongs to another subject")
    n = len(list(ctx.db.scalars(select(StudyGuideSection.id).where(StudyGuideSection.pack_id == ctx.state["pack_id"]))))
    g = StudyGuideSection(pack_id=ctx.state["pack_id"], topic_id=a.topic_id, position=n, heading=a.heading,
                          content_md=a.content_md, cited_section_ids=a.cited_section_ids)
    ctx.db.add(g)
    ctx.db.flush()
    return {"guide_section_id": g.id, "position": n}


def draft_question_tool(ctx: ToolContext, a: DraftArgs) -> dict[str, object]:
    if a.practice_exam_number > ctx.state["n_exams"]:
        raise ToolError(f"practice_exam_number must be between 1 and {ctx.state['n_exams']}")
    _check_sections(ctx, a.cited_section_ids)
    total = round(sum(r.points for r in a.rubric), 2)
    if abs(total - a.points) > 0.01:
        raise ToolError(f"rubric points add up to {total} but the question is worth {a.points}")
    practice = ctx.db.scalar(select(PracticeExam).where(PracticeExam.pack_id == ctx.state["pack_id"],
                                                PracticeExam.number == a.practice_exam_number))
    if practice is None:
        raise ToolError("practice exam not found")
    if a.replaces_question_id:
        old = store.must_get(ctx.db, ExamQuestion, a.replaces_question_id, "question")
        if old.pack_id != ctx.state["pack_id"]:
            raise ToolError("question belongs to another pack")
        old.state = "replaced"
        position = old.position
    else:
        position = len([q for q in ctx.db.scalars(select(ExamQuestion).where(ExamQuestion.practice_exam_id == practice.id))
                        if q.state != "replaced"])
    q = ExamQuestion(practice_exam_id=practice.id, pack_id=ctx.state["pack_id"], topic_id=a.topic_id, position=position,
                     statement_md=a.statement_md, solution_md=a.solution_md,
                     rubric=[r.model_dump() for r in a.rubric], points=a.points, cited_section_ids=a.cited_section_ids)
    ctx.db.add(q)
    ctx.db.flush()
    return {"question_id": q.id, "state": "draft", "replaces": a.replaces_question_id, "next": "call verify_question"}


async def verify_question_tool(ctx: ToolContext, a: QuestionArg) -> dict[str, object]:
    q = store.must_get(ctx.db, ExamQuestion, a.question_id, "question")
    if q.pack_id != ctx.state["pack_id"]:
        raise ToolError("question belongs to another pack")
    if q.state == "replaced":
        raise ToolError("question was replaced; verify the new one")
    sections = _check_sections(ctx, q.cited_section_ids)
    version, prompt = load_prompt("exam_verifier")
    cited = "\n\n".join(f"[{s.id}] {s.heading}\n{s.content_md[:4000]}" for s in sections)
    rubric = "\n".join(f"- {r['criterion']} ({r['points']} pts)" for r in q.rubric)
    ctx.db.commit()
    try:
        result, _ = await ctx.llm.structured("exam_verification", [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"QUESTION ({q.points} pts):\n{q.statement_md}\n\nSOLUTION:\n{q.solution_md}\n\n"
                                        f"RUBRIC:\n{rubric}\n\nCITED NOTES:\n{cited}"},
        ], Verification, ctx=ctx.call_ctx(), reason="exam self-check")
    except LLMUnavailable as exc:
        raise ToolError(f"verification model unavailable: {exc}") from exc
    if result is None:
        raise ToolError("verifier returned invalid output twice; call verify_question again")
    passed = result.solvable_with_given_data and result.units_consistent and result.answer_supported_by_notes
    q.state = "verified" if passed else "rejected"
    q.verification = {**result.model_dump(), "passed": passed, "prompt": f"exam_verifier@v{version}",
                      "checked_at": utcnow().isoformat()}
    return {"question_id": q.id, "passed": passed, **result.model_dump(),
            "next": "ok" if passed else "redraft with draft_question(replaces_question_id=...) fixing the issues"}


def save_exam_pack_tool(ctx: ToolContext, a: SaveArgs) -> dict[str, object]:
    pack = _pack(ctx)
    n_exams, n_q = ctx.state["n_exams"], ctx.state["n_questions"]
    problems = []
    practices = {m.number: m for m in ctx.db.scalars(select(PracticeExam).where(PracticeExam.pack_id == pack.id))}
    for num in range(1, n_exams + 1):
        practice = practices.get(num)
        qs = [q for q in ctx.db.scalars(select(ExamQuestion).where(ExamQuestion.practice_exam_id == practice.id))
              if q.state != "replaced"] if practice else []
        verified = [q for q in qs if q.state == "verified"]
        pending = [q.id for q in qs if q.state != "verified"]
        if len(verified) < n_q:
            problems.append(f"practice exam {num} has {len(verified)} verified questions, needs {n_q}")
        if pending:
            problems.append(f"practice exam {num} has unverified/rejected questions {pending}: verify or replace them")
    guide = list(ctx.db.scalars(select(StudyGuideSection).where(StudyGuideSection.pack_id == pack.id)))
    if not guide:
        problems.append("the study guide is empty: add study guide sections")
    if problems:
        raise ToolError("Exam pack is not complete: " + "; ".join(problems))
    for meta in a.practice_exams:
        if meta.number in practices:
            practices[meta.number].title, practices[meta.number].duration_minutes = meta.title, meta.duration_minutes
    transition(EXAM_PACK, pack, "ready")
    pack.built_at = utcnow()
    return {"pack_id": pack.id, "state": pack.state, "study_guide_sections": len(guide), "practice_exams": n_exams}


def exam_tools() -> list[Tool]:
    return [
        Tool("get_exam_scope", "Exam, topics with note section ids, course memory, requirements, what is new.",
             NoArgs, get_exam_scope_tool),
        Tool("search_notes", "Semantic search over this subject's notes.", SearchArgs, search_notes_tool),
        Tool("read_sections", "Read the full content of note sections by id.", ReadSectionsArgs, read_sections_tool),
        Tool("get_past_exams", "Past real exams uploaded for this subject (style and difficulty reference).",
             NoArgs, get_past_exams_tool),
        Tool("add_study_guide_section", "Add one study guide section (per topic), citing note sections.", GuideArgs,
             add_study_guide_section_tool),
        Tool("draft_question", "Draft (or replace) one practice exam question with solution, rubric and citations.",
             DraftArgs, draft_question_tool),
        Tool("verify_question", "Self-check a drafted question (solvable, units, supported by cited notes).",
             QuestionArg, verify_question_tool),
        Tool("save_exam_pack", "Finalize the pack. Fails with the list of problems if anything is missing.",
             SaveArgs, save_exam_pack_tool, terminal=True),
    ]

