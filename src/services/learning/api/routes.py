from fastapi import APIRouter, Depends, HTTPException
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List
from uuid import UUID, uuid4 
from datetime import datetime
import json

# --- SCHEMAS ---
from src.services.learning.api.schemas import (
    CreateExamRequest, ExamResponse,
    StyleRequest, StyleResponse,
    CreatePlanRequest, PlanSessionResponse,
    TaskStatusResponse # Nuevo schema para polling
)
from src.services.learning.domain.entities import ExamConfig

# --- LÓGICA ---
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.study_planner import GlobalStudyPlanner, ExamInput, UserPreferences

# --- INFRAESTRUCTURA ASYNC ---
from src.shared.infrastructure.rabbitmq import RabbitMQProducer
from src.shared.database.redis_client import RedisClient # Asumo que tienes un wrapper, si no usaremos redis directo

# --- DEPENDENCIAS ---
from src.api.dependencies import get_style_selector
# (Si usas inyección de dependencias para repositorios, impórtalos aquí)
from src.shared.database.repositories import PatternRepository

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)

# Configuración RabbitMQ
rabbit_producer = RabbitMQProducer()
EXAM_QUEUE_NAME = "exam.generate.job"

# =============================================================================
# ENDPOINTS
# =============================================================================

# --- 1. SUGERENCIA DE ESTILO ---
@router.post("/style/suggest", response_model=StyleResponse)
async def suggest_exam_style(
    request: StyleRequest,
    repo: PatternRepository = Depends(PatternRepository) 
):
    selector = StyleSelector(repo)
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

# --- 2. PLANIFICADOR (Síncrono porque es cálculo matemático rápido) ---
@router.post("/plans", response_model=List[PlanSessionResponse])
async def generate_plan(request: CreatePlanRequest):
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
    schedule = await loop.run_in_executor(executor, planner.generate_schedule, logic_exams, logic_prefs)
    
    return [
        PlanSessionResponse(exam_id=s.exam_id, date=s.date, 
                           duration=s.duration, focus_score=s.focus_score) 
        for s in schedule
    ]

# --- 3. GENERADOR DE EXÁMENES (ASÍNCRONO / FIRE-AND-FORGET) ---
@router.post("/exams/generate", status_code=202)
async def request_exam_generation(request: CreateExamRequest):
    """
    1. Recibe petición.
    2. Encola en RabbitMQ.
    3. Devuelve Task ID inmediatamente.
    """
    try:
        task_id = str(uuid4())
        
        # Payload del mensaje para el Worker
        job_payload = {
            "task_id": task_id,
            "student_id": str(request.student_id),
            "course_id": request.course_id,
            "cognitive_type": request.cognitive_type.value, # Enum a string
            "difficulty": request.difficulty.value,
            "topics": request.topics
        }
        
        print(f"📨 [API] Encolando trabajo {task_id} en {EXAM_QUEUE_NAME}")
        
        # Publicar en RabbitMQ
        # Nota: Asegúrate de que tu RabbitMQProducer maneje la conexión correctamente
        rabbit_producer.publish(
            queue_name=EXAM_QUEUE_NAME, 
            message=job_payload # Tu producer probablemente serializa a JSON dentro
        )
        
        # Marcar estado inicial en Redis (Opcional, para que el polling no de 404 al inicio)
        # redis_client.set(f"task:{task_id}", "QUEUED")

        return {
            "message": "Generación iniciada. Usa el task_id para consultar estado.",
            "task_id": task_id,
            "status": "QUEUED"
        }

    except Exception as e:
        print(f"❌ Error encolando: {e}")
        raise HTTPException(status_code=500, detail="Error interno del broker de mensajería")

# --- 4. POLLING DE ESTADO (Para que el Frontend sepa cuándo descargar) ---
@router.get("/exams/status/{task_id}")
async def check_exam_status(task_id: str):
    """
    Consulta Redis/DB para ver si el PDF ya está en MinIO.
    """
    # TODO: Implementar lectura de Redis real
    # status = redis_client.get(f"task:{task_id}")
    
    # MOCK TEMPORAL PARA QUE PRUEBES EL FLUJO (Borrar al implementar worker real)
    return {
        "task_id": task_id,
        "status": "PROCESSING", # Cambiará a 'COMPLETED' cuando el worker acabe
        "download_url": None
    }