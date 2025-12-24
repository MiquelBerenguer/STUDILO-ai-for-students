from enum import Enum
from typing import List, Optional, Union, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

# --- 1. VOCABULARIO (ENUMS) ---

class EngineeringBranch(str, Enum):
    COMPUTER_SCIENCE = "cs"
    CIVIL = "civil"
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    INDUSTRIAL = "industrial"
    CHEMICAL = "chemical"
    AEROSPACE = "aerospace"
    BIOMEDICAL = "biomedical"
    TELECOMMUNICATIONS = "teleco"

class CognitiveType(str, Enum):
    COMPUTATIONAL = "computational" # Procedural / Cálculo
    CONCEPTUAL = "conceptual"       # Declarativo / Teoría
    DESIGN_ANALYSIS = "design"      # Análisis de sistemas
    DEBUGGING = "debugging"         # Evaluación / Troubleshooting

class ExamDifficulty(str, Enum):
    FUNDAMENTAL = "fundamental"
    APPLIED = "applied"
    COMPLEX = "complex"
    GATEKEEPER = "gatekeeper"       # Nivel "Filtro"

class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    NUMERIC_INPUT = "numeric_input"
    CODE_EDITOR = "code_editor"
    OPEN_TEXT = "open_text"

class SourceType(str, Enum):
    OFFICIAL_EXAM = "official_exam"
    PROBLEM_SET = "problem_set"
    LAB_NOTES = "lab_notes"
    THEORY_SLIDES = "theory_slides"

# --- 2. REGLAS DE VALIDACIÓN (POLIMORFISMO) ---

class NumericalValidation(BaseModel):
    type: Literal["numeric"] = "numeric" # Discriminador para DB
    correct_value: float
    tolerance_percentage: float = 5.0
    allowed_units: List[str] = Field(default_factory=list)

class CodeTestCase(BaseModel):
    input_data: str
    expected_output: str
    is_hidden: bool = False

class CodeValidation(BaseModel):
    type: Literal["code"] = "code" # Discriminador
    language: str = "python"
    test_cases: List[CodeTestCase]
    forbidden_keywords: Optional[List[str]] = None

class MultipleChoiceValidation(BaseModel):
    type: Literal["choice"] = "choice" # Discriminador
    options: List[str]
    correct_index: int

# Type alias para uso en Pydantic
ValidationRule = Union[NumericalValidation, CodeValidation, MultipleChoiceValidation, None]

# --- 3. CONTEXTO ACADÉMICO ---

class PedagogicalPattern(str, Enum):
    LINEAR = "linear"
    SPIRAL = "spiral"
    ADAPTIVE = "adaptive"
    PROJECT_BASED = "pbl"

# --- AÑADIR ESTO EN entities.py PARA QUE REPOSITORIES NO FALLE ---

class PatternScope(str, Enum):
    GLOBAL = "global"           # Estilo estándar de TutorIA
    UNIVERSITY = "university"   # Estilo específico (ej: UPC, UNAM)
    COURSE = "course"           # Estilo de la asignatura
    PERSONAL = "personal"       # Adaptado al alumno

class Pattern(BaseModel):
    """
    Representa un 'Estilo de Examen' guardado en DB.
    El repositorio devuelve esto, así que necesitamos definirlo.
    """
    id: str
    name: str
    description: str
    scope: PatternScope
    # Usamos nuestro nuevo Enum de pedagogía
    pedagogical_pattern: PedagogicalPattern 
    
    # Receta para el LLM (el ADN del estilo)
    reasoning_recipe: str 
    original_question_example: Optional[str] = None

class EngineeringBlock(BaseModel):
    """Unidad de conocimiento extraído (RAG)"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    course_id: str
    source_type: SourceType
    
    clean_text: str
    latex_content: Optional[str] = None
    code_snippet: Optional[str] = None
    image_urls: List[str] = Field(default_factory=list)
    
    topics: List[str]
    is_problem: bool
    complexity: float = Field(ge=0.0, le=1.0)
    
    # Grafo de dependencias (Spiral Learning)
    prerequisite_block_ids: List[str] = Field(default_factory=list)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)

# --- 4. MODELO DE EXAMEN ---

class GeneratedQuestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Contenido visual
    statement_latex: str
    context_image_url: Optional[str] = None
    code_context: Optional[str] = None
    
    # Metadatos
    cognitive_type: CognitiveType
    difficulty: ExamDifficulty
    question_type: QuestionType
    source_block_id: str
    
    # Lógica de Evaluación (La magia)
    validation_rules: ValidationRule
    
    # Pedagogía
    step_by_step_solution_latex: str
    hint: Optional[str] = None

class ExamConfig(BaseModel):
    student_id: str
    course_id: str
    target_difficulty: ExamDifficulty = ExamDifficulty.APPLIED
    pattern: PedagogicalPattern = PedagogicalPattern.ADAPTIVE
    
    topics_include: List[str] = Field(default_factory=list)
    num_questions: int = 5
    include_code_questions: bool = True

class StudentAttempt(BaseModel):
    question_id: str
    raw_answer: str
    is_correct: bool
    time_spent_seconds: int
    feedback_generated: Optional[str] = None

class Exam(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    config: ExamConfig
    questions: List[GeneratedQuestion]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "created"
    score: Optional[float] = None
    attempts: List[StudentAttempt] = Field(default_factory=list)