from fastapi import APIRouter, Depends, HTTPException
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List

# Schemas
from src.services.learning.api.schemas import (
    CreateExamRequest, ExamResponse,
    StyleRequest, StyleResponse,
    CreatePlanRequest, PlanSessionResponse
)

# Lógica
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.study_planner import GlobalStudyPlanner, ExamInput, UserPreferences

# Dependencias (LA CLAVE DE QUE ESTO FUNCIONE)
from src.api.dependencies import get_style_selector

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4) # Para el planner matemático

# --- ENDPOINT 1: SUGERENCIA DE ESTILO (Probado y Funciona) ---
@router.post("/style/suggest", response_model=StyleResponse)
async def suggest_exam_style(
    request: StyleRequest,
    selector: StyleSelector = Depends(get_style_selector) # <--- INYECCIÓN AUTOMÁTICA
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

# --- ENDPOINT 2: PLANIFICADOR (Adaptado para no bloquear) ---
@router.post("/plans", response_model=List[PlanSessionResponse])
async def generate_plan(request: CreatePlanRequest):
    """
    Ejecuta el algoritmo matemático en un hilo separado para no congelar la API.
    """
    # 1. Adaptar Datos (Schema -> Logic)
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
    
    # 2. Instanciar Planner (Es lógica pura, no necesita DB por ahora)
    planner = GlobalStudyPlanner()
    
    # 3. Ejecutar SIN BLOQUEAR (Offloading to thread)
    loop = asyncio.get_event_loop()
    schedule = await loop.run_in_executor(
        executor, 
        planner.generate_schedule, 
        logic_exams, 
        logic_prefs
    )
    
    # 4. Retornar
    return [
        PlanSessionResponse(
            exam_id=s.exam_id,
            date=s.date,
            duration=s.duration,
            focus_score=s.focus_score
        ) for s in schedule
    ]

# --- ENDPOINT 3: EXAM GENERATOR (Placeholder hasta conectar AI Service) ---
@router.post("/exams/generate", response_model=ExamResponse)
async def generate_exam(
    request: CreateExamRequest,
    # generator: ExamGenerator = Depends(get_exam_generator) # Pendiente
):
    # Por ahora devolvemos un mock para validar que la ruta existe
    return ExamResponse(exam_id="mock-exam-123")