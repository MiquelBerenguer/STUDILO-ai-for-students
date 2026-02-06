from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from uuid import uuid4
from datetime import datetime
import logging

# --- SCHEMAS (Contratos de Datos) ---
from src.services.learning.api.schemas import (
    CreateExamRequest, ExamResponse,
    StyleRequest, StyleResponse,
    CreatePlanRequest, PlanSessionResponse,
    ChatRequest, ChatResponse,
    TaskStatusResponse,
    ExamSubmissionRequest, ExamResultResponse,
    CourseCreate, CourseResponse # <--- NECESARIO para la nueva funcionalidad
)

# --- LÓGICA DE NEGOCIO ---
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.study_planner import GlobalStudyPlanner, ExamInput, UserPreferences
from src.services.learning.logic.professor_agent import professor_agent 
from src.services.ai.service import AIService
from src.services.learning.logic.grader import GraderEngine
from src.services.learning.domain.entities import GeneratedQuestion, QuestionType, NumericalValidation

# --- INFRAESTRUCTURA ---
from app.core.rabbitmq import mq_client
from src.shared.database.database import get_db
from src.shared.database.repositories import PatternRepository
from src.shared.database.models import User, Student, Course
from app.dependencies import get_current_user 

# CONFIGURACIÓN
router = APIRouter()
logger = logging.getLogger(__name__)

# =============================================================================
# 🏭 FACTORIES (Inyección de Dependencias)
# =============================================================================
def get_ai_service() -> AIService:
    return AIService()

def get_grader_engine(ai_service: AIService = Depends(get_ai_service)) -> GraderEngine:
    return GraderEngine(ai_service=ai_service, cache_service=None)

def get_pattern_repo(db: Session = Depends(get_db)) -> PatternRepository:
    return PatternRepository(db)

# =============================================================================
# 🏛 SERVICE LAYER (Helpers para Cursos y Estudiantes)
# =============================================================================
class CourseService:
    """Gestiona la creación de perfiles y asignaturas de forma limpia."""
    
    @staticmethod
    def get_or_create_student(db: Session, user: User) -> Student:
        student = db.query(Student).filter(Student.auth_user_id == user.id).first()
        if not student:
            logger.info(f"Creando perfil de estudiante para usuario: {user.email}")
            student = Student(
                id=uuid4(),
                auth_user_id=user.id,
                email=user.email,
                university_name="TutorIA University", 
                degree_name="Ingeniería General"
            )
            db.add(student)
            db.commit()
            db.refresh(student)
        return student

    @staticmethod
    def create_course(db: Session, user: User, course_data: CourseCreate) -> Course:
        student = CourseService.get_or_create_student(db, user)
        
        # Verificar duplicados para evitar errores
        exists = db.query(Course).filter(
            Course.student_id == student.id,
            Course.name == course_data.name
        ).first()
        
        if exists:
            # Si ya existe, lanzamos error 400 para avisar al frontend
            raise HTTPException(status_code=400, detail=f"La asignatura '{course_data.name}' ya existe.")

        new_course = Course(
            id=uuid4(),
            student_id=student.id,
            name=course_data.name,
            domain_field=course_data.domain_field,
            cognitive_type='procedural',
            semester=course_data.semester,
            color_theme=course_data.color_theme
        )
        db.add(new_course)
        db.commit()
        db.refresh(new_course)
        return new_course

# =============================================================================
# 🎓 0. GESTIÓN DE CURSOS (NUEVO - IMPRESCINDIBLE)
# =============================================================================
@router.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED, tags=["Courses"])
async def create_course_endpoint(
    course_in: CourseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return CourseService.create_course(db, current_user, course_in)

@router.get("/courses", response_model=List[CourseResponse], tags=["Courses"])
async def list_courses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    student = CourseService.get_or_create_student(db, current_user)
    return db.query(Course).filter(Course.student_id == student.id).all()

# =============================================================================
# 🧠 1. CHAT DEL MENTOR
# =============================================================================
@router.post("/chat/ask", response_model=ChatResponse, tags=["Mentoring"])
async def ask_mentor(
    request: ChatRequest, 
    current_user: User = Depends(get_current_user)
):
    try:
        return await professor_agent.ask(request)
    except Exception as e:
        logger.error(f"Mentor Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="El Mentor está desconectado temporalmente.")

# =============================================================================
# 🎨 2. SUGERENCIA DE ESTILO
# =============================================================================
@router.post("/style/suggest", response_model=StyleResponse, tags=["Exams"])
async def suggest_exam_style(
    request: StyleRequest,
    repo: PatternRepository = Depends(get_pattern_repo),
    current_user: User = Depends(get_current_user)
):
    selector = StyleSelector(repo)
    pattern = await selector.select_best_pattern(
        course_id=request.course_id,
        domain=request.domain,
        cognitive_needed=request.cognitive_type,
        difficulty=request.difficulty
    )
    
    if not pattern:
        return StyleResponse(
            pattern_id="default",
            reasoning_recipe="Standard Step-by-Step",
            source="system_fallback"
        )
    
    return StyleResponse(
        pattern_id=pattern.id,
        reasoning_recipe=pattern.reasoning_recipe,
        original_question=pattern.original_question,
        source=pattern.scope.value
    )

# =============================================================================
# 📅 3. PLANIFICADOR DE ESTUDIO (OPTIMIZADO)
# =============================================================================
@router.post("/plans", response_model=List[PlanSessionResponse], tags=["Planning"])
async def generate_plan(
    request: CreatePlanRequest, 
    current_user: User = Depends(get_current_user)
):
    # Mapeo de datos
    logic_exams = [
        ExamInput(id=e.id, name=e.name, exam_date=e.exam_date, 
                  difficulty_level=e.difficulty_level, topics_count=e.topics_count) 
        for e in request.exams
    ]
    logic_prefs = UserPreferences(
        availability_slots=request.availability_slots,
        force_include_ids=request.force_include_ids
    )
    
    planner = GlobalStudyPlanner()
    
    try:
        # MEJORA: Usamos run_in_threadpool nativo de FastAPI en vez de executor manual
        schedule = await run_in_threadpool(
            planner.generate_schedule, 
            logic_exams, 
            logic_prefs
        )
        return [
            PlanSessionResponse(exam_id=s.exam_id, date=s.date, 
                              duration=s.duration, focus_score=s.focus_score) 
            for s in schedule
        ]
    except Exception as e:
        logger.error(f"Planner Error: {e}")
        raise HTTPException(status_code=400, detail="No se pudo generar el plan.")

# =============================================================================
# 📝 4. GENERADOR DE EXÁMENES (RabbitMQ)
# =============================================================================
@router.post("/exams/generate", status_code=202, tags=["Exams"])
async def request_exam_generation(
    request: CreateExamRequest,
    current_user: User = Depends(get_current_user)
):
    task_id = str(uuid4())
    
    job_payload = {
        "task_id": task_id,
        "user_id": str(current_user.id),
        "student_id": str(request.student_id) if request.student_id else None,
        "course_id": str(request.course_id) if request.course_id else None,
        # Seguridad extra para Enums
        "difficulty": request.difficulty.value if hasattr(request.difficulty, 'value') else request.difficulty,
        "topic": getattr(request, "topic", "General"),
        "document_id": str(request.document_id) if request.document_id else None,
        "created_at": datetime.utcnow().timestamp()
    }
    
    success = await mq_client.send_message(job_payload)
    
    if not success:
        logger.critical("RabbitMQ is down!")
        raise HTTPException(status_code=503, detail="El servicio de generación está saturado.")
    
    return {
        "message": "El Profesor está redactando tu examen.",
        "task_id": task_id,
        "status": "QUEUED"
    }

# =============================================================================
# 🔍 5. POLLING DE ESTADO
# =============================================================================
@router.get("/exams/status/{task_id}", response_model=TaskStatusResponse, tags=["Exams"])
async def check_exam_status(
    task_id: str, 
    current_user: User = Depends(get_current_user)
):
    return {
        "task_id": task_id,
        "status": "PROCESSING",
        "download_url": None
    }

# =============================================================================
# ✅ 6. CORRECCIÓN INTELIGENTE
# =============================================================================
@router.post("/exams/submit", response_model=ExamResultResponse, tags=["Exams"])
async def submit_exam_attempt(
    submission: ExamSubmissionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    grader: GraderEngine = Depends(get_grader_engine)
):
    """Calcula nota, XP y feedback detallado usando GraderEngine."""
    
    # 1. Recuperar la "Verdad" (Mock temporal)
    original_questions = await _fetch_questions_source(submission.exam_id, db)
    
    if not original_questions:
        raise HTTPException(status_code=404, detail="Examen no encontrado.")

    # 2. Ejecutar Corrección
    try:
        grading_result = await grader.grade_exam(
            exam_questions=original_questions,
            answers=submission.answers
        )
        
        return ExamResultResponse(
            exam_id=submission.exam_id,
            total_score=grading_result["total_score"],
            xp_earned=grading_result["xp_earned"],
            details=grading_result["details"],
            meta=grading_result.get("meta", {})
        )

    except Exception as e:
        logger.error(f"Grader Crash: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno durante la corrección.")

# --- HELPER MOCK (Para mantener funcionalidad sin DB completa aún) ---
async def _fetch_questions_source(exam_id, db) -> List[GeneratedQuestion]:
    return [
        GeneratedQuestion(
            id="q1", 
            statement_latex="Un coche acelera a 2m/s^2 durante 10s desde reposo. Calcule vf.", 
            cognitive_type="computational", 
            difficulty="applied",
            question_type=QuestionType.NUMERIC_INPUT,
            source_block_id="block_1",
            step_by_step_solution_latex="v = a * t",
            validation_rules=NumericalValidation(
                correct_value=20.0,
                allowed_units=["m/s"],
                tolerance_percentage=5.0
            )
        )
    ]