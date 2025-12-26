from fastapi import APIRouter, Depends, HTTPException, status
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List
from uuid import uuid4
from datetime import datetime
from sqlalchemy.orm import Session

# --- SCHEMAS ---
from src.services.learning.api.schemas import (
    CreateExamRequest, ExamResponse,
    StyleRequest, StyleResponse,
    CreatePlanRequest, PlanSessionResponse,
    ChatRequest, ChatResponse,
    TaskStatusResponse
)
# --- LÓGICA DE NEGOCIO ---
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.study_planner import GlobalStudyPlanner, ExamInput, UserPreferences
from src.services.learning.logic.professor_agent import professor_agent 

# --- INFRAESTRUCTURA Y SEGURIDAD ---
from app.core.rabbitmq import mq_client
from src.shared.database.database import get_db
from src.shared.database.repositories import PatternRepository
from src.shared.database.models import User

# CORRECCIÓN DE CONECTIVIDAD: Importamos desde dependencies para evitar ciclos
from app.dependencies import get_current_user 

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)

# =============================================================================
# 🧠 1. CHAT DEL MENTOR (EL PROFESOR)
# =============================================================================
@router.post("/chat/ask", response_model=ChatResponse)
async def ask_mentor(
    request: ChatRequest,
    current_user: User = Depends(get_current_user) # PROTEGIDO
):
    """
    Endpoint del Tutor IA.
    """
    try:
        # En el futuro pasaremos current_user.full_name al agente para que sea personalizado
        return await professor_agent.ask(request)
    except Exception as e:
        print(f"❌ Error TutorIA: {e}")
        raise HTTPException(
            status_code=500, 
            detail="El Mentor está teniendo problemas técnicos."
        )

# =============================================================================
# 🎨 2. SUGERENCIA DE ESTILO
# =============================================================================
def get_pattern_repo(db: Session = Depends(get_db)):
    return PatternRepository(db)

@router.post("/style/suggest", response_model=StyleResponse)
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
# 📅 3. PLANIFICADOR DE ESTUDIO
# =============================================================================
@router.post("/plans", response_model=List[PlanSessionResponse])
async def generate_plan(
    request: CreatePlanRequest,
    current_user: User = Depends(get_current_user)
):
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
    loop = asyncio.get_event_loop()
    
    try:
        schedule = await loop.run_in_executor(
            executor, 
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
        raise HTTPException(status_code=400, detail=f"Error generando plan: {str(e)}")

# =============================================================================
# 📝 4. GENERADOR DE EXÁMENES (RabbitMQ Asíncrono)
# =============================================================================
@router.post("/exams/generate", status_code=202)
async def request_exam_generation(
    request: CreateExamRequest,
    current_user: User = Depends(get_current_user)
):
    task_id = str(uuid4())
    
    job_payload = {
        "task_id": task_id,
        "user_id": str(current_user.id),
        "student_id": str(request.student_id),
        "course_id": request.course_id,
        "difficulty": request.difficulty if isinstance(request.difficulty, str) else request.difficulty.value,
        "topics": getattr(request, "topics", []),
        "created_at": datetime.utcnow().timestamp()
    }
    
    success = await mq_client.send_message(job_payload)
    
    if not success:
        raise HTTPException(status_code=503, detail="Sistema de colas no disponible")
    
    return {
        "message": "El Profesor está redactando tu examen.",
        "task_id": task_id,
        "status": "QUEUED"
    }

# =============================================================================
# 🔍 5. POLLING DE ESTADO
# =============================================================================
@router.get("/exams/status/{task_id}", response_model=TaskStatusResponse)
async def check_exam_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    return {
        "task_id": task_id,
        "status": "PROCESSING",
        "download_url": None
    }