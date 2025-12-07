from fastapi import APIRouter, Depends, HTTPException
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List
from uuid import UUID, uuid4 # Importación necesaria añadida

# Schemas
from src.services.learning.api.schemas import (
    CreateExamRequest, ExamResponse,
    StyleRequest, StyleResponse,
    CreatePlanRequest, PlanSessionResponse
)

# Lógica de Negocio
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.study_planner import GlobalStudyPlanner, ExamInput, UserPreferences

# Dependencias
from src.api.dependencies import get_style_selector

# --- NUEVAS IMPORTACIONES (PDF) ---
from src.shared.queue.models import PDFGenerationJob, CognitiveType
from src.shared.infrastructure.rabbitmq import RabbitMQProducer

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)

# --- INSTANCIA DEL PRODUCTOR DE RABBITMQ ---
rabbit_producer = RabbitMQProducer()
PDF_QUEUE_NAME = "pdf_generation_queue"

# --- ENDPOINT 1: SUGERENCIA DE ESTILO ---
@router.post("/style/suggest", response_model=StyleResponse)
async def suggest_exam_style(
    request: StyleRequest,
    selector: StyleSelector = Depends(get_style_selector)
):
    print(f"🔍 Buscando estilo para: {request.domain}")
    pattern = await selector.select_best_pattern(
        course_id=request.course_id,
        domain=request.domain,
        cognitive_needed=request.cognitive_type,
        difficulty=request.difficulty
    )
    
    if not pattern:
        raise HTTPException(status_code=404, detail="No patterns found")
    
    return StyleResponse(
        pattern_id=pattern.id,
        reasoning_recipe=pattern.reasoning_recipe,
        original_question=pattern.original_question,
        source=pattern.scope.value
    )

# --- ENDPOINT 2: PLANIFICADOR ---
@router.post("/plans", response_model=List[PlanSessionResponse])
async def generate_plan(request: CreatePlanRequest):
    logic_exams = [
        ExamInput(
            id=e.id, 
            name=e.name, 
            exam_date=e.exam_date, 
            difficulty_level=e.difficulty_level,
            topics_count=e.topics_count
        ) for e in request.exams
    ]
    
    logic_prefs = UserPreferences(
        availability_slots=request.availability_slots,
        force_include_ids=request.force_include_ids
    )
    
    planner = GlobalStudyPlanner()
    
    loop = asyncio.get_event_loop()
    schedule = await loop.run_in_executor(
        executor, 
        planner.generate_schedule, 
        logic_exams, 
        logic_prefs
    )
    
    return [
        PlanSessionResponse(
            exam_id=s.exam_id,
            date=s.date,
            duration=s.duration,
            focus_score=s.focus_score
        ) for s in schedule
    ]

# --- ENDPOINT 3: EXAM GENERATOR ---
@router.post("/exams/generate", response_model=ExamResponse)
async def generate_exam(request: CreateExamRequest):
    return ExamResponse(exam_id="mock-exam-123")

# --- ENDPOINT 4: GENERAR PDF (ASYNC / RABBITMQ) ---
@router.post("/exams/{exam_id}/pdf", status_code=202)
async def request_exam_pdf(
    exam_id: UUID, 
    cognitive_type: CognitiveType, 
    user_id: UUID 
):
    """
    Solicita la generación de un PDF.
    Retorna inmediatamente (Asíncrono) para no bloquear el servidor.
    """
    try:
        # 1. ID de tarea para logs
        task_id = uuid4()
        
        # 2. Creamos el objeto del trabajo
        job = PDFGenerationJob(
            task_id=task_id,
            user_id=user_id,
            exam_id=exam_id,
            cognitive_type=cognitive_type,
            include_solutions=False
        )
        
        # 3. Publicamos en RabbitMQ
        print(f"📨 Enviando trabajo PDF a la cola: {PDF_QUEUE_NAME}")
        rabbit_producer.publish(queue_name=PDF_QUEUE_NAME, message=job.dict())
        
        return {
            "message": "Generación de PDF iniciada.",
            "task_id": task_id,
            "status": "queued"
        }
        
    except Exception as e:
        print(f"❌ Error enviando a RabbitMQ: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")