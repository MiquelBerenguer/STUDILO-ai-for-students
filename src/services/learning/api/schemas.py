from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union, Literal
from datetime import date
from src.services.learning.domain.entities import ExamDifficulty, CognitiveType

# =============================================================================
# 🟢 1. GENERACIÓN Y PLANIFICACIÓN (LEGACY + MEJORAS)
# =============================================================================

class CreateExamRequest(BaseModel):
    student_id: str
    course_id: str
    
    # SOPORTE HÍBRIDO: Aceptamos string ("facil") o Enum (ExamDifficulty.FUNDAMENTAL)
    difficulty: Union[str, ExamDifficulty] = Field(default="medium") 
    num_questions: int = Field(default=5, ge=1, le=50)
    
    # CRÍTICO: Añadido para que el generador sepa qué temas incluir (Tarea 4.1)
    topics_include: List[str] = Field(default_factory=list, description="Lista de temas específicos a evaluar")

    @field_validator('difficulty')
    def normalize_difficulty(cls, v):
        if isinstance(v, ExamDifficulty):
            return v
        
        v_str = str(v).lower().strip()
        mapping = {
            "facil": ExamDifficulty.FUNDAMENTAL, "easy": ExamDifficulty.FUNDAMENTAL, 
            "fundamental": ExamDifficulty.FUNDAMENTAL, "beginner": ExamDifficulty.FUNDAMENTAL,
            "medio": ExamDifficulty.APPLIED, "medium": ExamDifficulty.APPLIED, 
            "applied": ExamDifficulty.APPLIED, "intermedio": ExamDifficulty.APPLIED,
            "dificil": ExamDifficulty.COMPLEX, "hard": ExamDifficulty.COMPLEX, 
            "complex": ExamDifficulty.COMPLEX, "avanzado": ExamDifficulty.COMPLEX,
            "gatekeeper": ExamDifficulty.GATEKEEPER
        }
        return mapping.get(v_str, ExamDifficulty.APPLIED)

class StyleRequest(BaseModel):
    course_id: str
    domain: str
    cognitive_type: CognitiveType
    difficulty: ExamDifficulty

class PlanExamInput(BaseModel):
    id: str
    name: str
    exam_date: date
    difficulty_level: int
    topics_count: int = 1

class CreatePlanRequest(BaseModel):
    student_id: str
    exams: List[PlanExamInput]
    availability_slots: Dict[str, int]
    force_include_ids: List[str] = []

class ExamResponse(BaseModel):
    exam_id: str
    status: str = "generated"

class StyleResponse(BaseModel):
    pattern_id: str
    reasoning_recipe: str
    original_question: Optional[str] = None
    source: str

class PlanSessionResponse(BaseModel):
    exam_id: str
    date: date
    duration: int
    focus_score: float

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    download_url: Optional[str] = None

# =============================================================================
# 🔵 2. CHAT DEL TUTOR (LEGACY)
# =============================================================================

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    message: str
    context_files: List[str] = [] 
    conversation_history: List[Message] = [] 
    course_context: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    methodology_step: str 
    sources: List[str] = []

# =============================================================================
# 🟠 3. CORRECCIÓN Y FEEDBACK (TAREA 4.6)
# =============================================================================

class AnswerSubmission(BaseModel):
    question_id: str = Field(..., description="UUID de la pregunta.")
    numeric_value: Optional[str] = Field(None, description="Valor numérico puro. Ej: '10.5'")
    unit: Optional[str] = Field(None, description="Unidad utilizada. Ej: 'm/s'")
    text_content: Optional[str] = Field(None, description="Procedimiento o razonamiento escrito.")
    time_spent_seconds: int = Field(0, ge=0, description="Tiempo dedicado en segundos.")

    @field_validator('numeric_value')
    def sanitize_numeric(cls, v):
        if v is not None:
            return v.strip().replace(',', '.')
        return v

class ExamSubmissionRequest(BaseModel):
    exam_id: str
    student_id: str
    answers: List[AnswerSubmission]

class QuestionFeedbackDetail(BaseModel):
    question_id: str
    score: float
    status: Literal["correct", "incorrect", "partial", "pending"]
    feedback_text: str
    correct_solution: Optional[str] = None
    source: Literal["computed", "ai", "cache", "fallback"] 

class ExamResultResponse(BaseModel):
    exam_id: str
    total_score: float
    xp_earned: int
    details: List[QuestionFeedbackDetail]
    meta: Dict[str, Any] = Field(default_factory=dict, description="Métricas de ejecución")

# --- INTERNAL AI SCHEMAS ---
class AIReasoningEvaluation(BaseModel):
    chain_of_thought: str = Field(..., description="Razonamiento interno.")
    error_type: Literal['calculation_error', 'conceptual_error', 'unit_error', 'minor_slip', 'correct']
    adjusted_score_percentage: float = Field(..., ge=0.0, le=100.0)
    feedback_text: str