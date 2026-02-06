from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Literal, Union, Dict, Optional, Any
from uuid import UUID
from datetime import datetime, date
from enum import Enum

# =============================================================================
# 1. ENUMS & CONSTANTS
# =============================================================================
class DomainFieldEnum(str, Enum):
    mathematics = "mathematics"
    physics = "physics"
    computer_science = "computer_science"
    electronics = "electronics"
    general_engineering = "general_engineering"

class DifficultyEnum(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

# Para mantener compatibilidad con tu código legacy
class ExamDifficulty(str, Enum):
    FUNDAMENTAL = "easy"
    APPLIED = "medium"
    COMPLEX = "hard"
    GATEKEEPER = "hard"

class ErrorTypeEnum(str, Enum):
    calculation = "calculation_error"
    conceptual = "conceptual_error"
    unit = "unit_error"
    minor_slip = "minor_slip"
    correct = "correct"

# =============================================================================
# 2. QUESTION CONTENT SCHEMAS
# =============================================================================

class TestCase(BaseModel):
    input_data: str = Field(..., description="Entrada del test")
    expected_output: str = Field(..., description="Salida esperada")
    is_hidden: bool = Field(False, description="Si es un test oculto")

class NumericContent(BaseModel):
    kind: Literal["numeric_input"] = "numeric_input"
    statement_latex: str = Field(..., description="Enunciado en LaTeX")
    explanation: str = Field(..., description="Explicación paso a paso")
    hint: Optional[str] = Field(None, description="Pista breve")
    numeric_solution: float = Field(..., description="Solución exacta")
    tolerance_percent: float = Field(..., description="Margen de error permitido (%)")
    units: List[str] = Field(default_factory=list, description="Unidades permitidas")

class ChoiceContent(BaseModel):
    kind: Literal["multiple_choice"] = "multiple_choice"
    statement_latex: str = Field(..., description="Enunciado en LaTeX")
    explanation: str = Field(..., description="Explicación")
    hint: Optional[str] = Field(None, description="Pista breve")
    options: List[str] = Field(..., min_items=2, description="Opciones disponibles")
    correct_option_index: int = Field(..., ge=0, description="Índice de la respuesta correcta")

class CodeContent(BaseModel):
    kind: Literal["code_editor"] = "code_editor"
    statement_latex: str = Field(..., description="Enunciado en LaTeX")
    explanation: str = Field(..., description="Explicación")
    hint: Optional[str] = Field(None, description="Pista breve")
    code_context: str = Field(..., description="Boilerplate inicial del código")
    test_cases: List[TestCase] = Field(..., description="Suite de tests")

# Unión discriminada para que Pydantic sepa qué tipo de pregunta es
QuestionContentVariant = Union[NumericContent, ChoiceContent, CodeContent]

class ReasoningQuestionResponse(BaseModel):
    chain_of_thought: str = Field(..., description="Razonamiento interno (CoT)")
    content: QuestionContentVariant

# =============================================================================
# 3. COURSES DOMAIN
# =============================================================================

class CourseBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    domain_field: DomainFieldEnum = Field(DomainFieldEnum.general_engineering)
    semester: int = Field(1, ge=1, le=12)
    color_theme: str = Field("#3498db", pattern=r"^#[0-9a-fA-F]{6}$")

class CourseCreate(CourseBase):
    pass

class CourseResponse(CourseBase):
    id: UUID
    student_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# 4. EXAM GENERATION & PLANNING
# =============================================================================

class CreateExamRequest(BaseModel):
    student_id: Optional[UUID] = None 
    course_id: Optional[UUID] = None
    topic: str = Field(..., min_length=3)
    
    # Validador inteligente para aceptar strings o Enums
    difficulty: Union[str, DifficultyEnum] = Field(default=DifficultyEnum.medium)
    num_questions: int = Field(default=3, ge=1, le=20)
    document_id: Optional[UUID] = None

    @field_validator('difficulty', mode='before')
    def normalize_difficulty(cls, v):
        if isinstance(v, DifficultyEnum):
            return v
        v_str = str(v).lower().strip()
        mapping = {
            "facil": DifficultyEnum.easy, "easy": DifficultyEnum.easy, 
            "fundamental": DifficultyEnum.easy,
            "medio": DifficultyEnum.medium, "medium": DifficultyEnum.medium, 
            "applied": DifficultyEnum.medium,
            "dificil": DifficultyEnum.hard, "hard": DifficultyEnum.hard, 
            "complex": DifficultyEnum.hard
        }
        return mapping.get(v_str, DifficultyEnum.medium)

class ExamResponse(BaseModel):
    task_id: str
    status: Literal["pending", "processing", "completed", "failed", "QUEUED"]
    message: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    download_url: Optional[str] = None

# =============================================================================
# 5. EXAM SUBMISSION & GRADING
# =============================================================================

class StudentAnswer(BaseModel):
    question_id: str
    selected_option: Optional[int] = None
    numeric_value: Optional[float] = None
    code_submission: Optional[str] = None
    # Campos legacy opcionales
    unit: Optional[str] = None
    text_content: Optional[str] = None

    @field_validator('numeric_value', mode='before')
    def sanitize_numeric(cls, v):
        """Convierte '2,5' en 2.5 automáticamente"""
        if isinstance(v, str):
            try:
                return float(v.strip().replace(',', '.'))
            except ValueError:
                return None
        return v

class ExamSubmissionRequest(BaseModel):
    exam_id: UUID
    student_id: Optional[UUID] = None
    answers: List[StudentAnswer]

# --- ¡¡AQUÍ FALTABA LA CLASE!! ---
class QuestionFeedbackDetail(BaseModel):
    question_id: str
    score: float
    status: Literal["correct", "incorrect", "partial", "pending"]
    feedback_text: str
    correct_solution: Optional[str] = None
    source: Literal["computed", "ai", "cache", "fallback"]
# ---------------------------------

class ExamResultResponse(BaseModel):
    exam_id: UUID
    total_score: float
    xp_earned: int
    details: Dict[str, Any]
    meta: Dict[str, Any]

class AIReasoningEvaluation(BaseModel):
    chain_of_thought: str = Field(..., description="Análisis del error del alumno.")
    error_type: ErrorTypeEnum = Field(..., description="Clasificación del error.")
    adjusted_score_percentage: float = Field(..., ge=0, le=100, description="Score calculado (0-100).")
    feedback_text: str = Field(..., description="Feedback pedagógico.")

# =============================================================================
# 6. LEGACY & UTILS
# =============================================================================

class StyleRequest(BaseModel):
    course_id: str
    domain: str
    cognitive_type: str
    difficulty: str

class StyleResponse(BaseModel):
    pattern_id: str
    reasoning_recipe: str
    original_question: Optional[str] = None
    source: str

class ExamInput(BaseModel):
    id: str
    name: str
    exam_date: date
    difficulty_level: int
    topics_count: int = 1

class CreatePlanRequest(BaseModel):
    exams: List[ExamInput]
    availability_slots: Dict[str, Any]
    force_include_ids: List[str]

class PlanSessionResponse(BaseModel):
    exam_id: str
    date: date
    duration: int
    focus_score: float

class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str