from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

# --- 1. ENUMS (Conservados y Ampliados) ---

class CognitiveType(str, Enum):
    PROCEDURAL = "procedural"        # Cálculo, Física (Pasos lógicos)
    DECLARATIVE = "declarative"      # Historia, Normativa
    INTERPRETATIVE = "interpretative"# Diseño, Ética
    CONCEPTUAL = "conceptual"        # Teoría de Sistemas

class ExamDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    INSANE = "insane" # Nivel Ingeniería "Examen Final Filtro"

class SourceType(str, Enum):
    OFFICIAL_EXAM = "official_exam"  # Examen real de años pasados
    CLASS_NOTES = "class_notes"      # Apuntes de alumno
    TEXTBOOK = "textbook"            # Bibliografía oficial

# --- 2. JERARQUÍA INSTITUCIONAL (NUEVO CORE) ---

class University(BaseModel):
    id: str
    name: str
    country: str

class Degree(BaseModel):
    id: str
    university_id: str
    name: str # Ej: "Ingeniería Informática"

class Course(BaseModel):
    id: str
    degree_id: str
    name: str # Ej: "Física II"
    year: int # Ej: 1, 2, 3, 4
    cognitive_type: CognitiveType

# --- 3. CONTENIDO SEMÁNTICO (INGESTA) ---

class MathBlock(BaseModel):
    """Representa un bloque de conocimiento extraído (Teoría o Problema)"""
    id: str
    course_id: str
    source_type: SourceType
    original_text: str  # Texto plano para búsqueda simple
    latex_content: str  # El tesoro: Contenido formateado en LaTeX
    topics: List[str]   # Ej: ["Derivadas", "Optimización"]
    is_problem: bool    # True si es un ejercicio, False si es teoría
    solution_latex: Optional[str] = None # Si venía con solución

# --- 4. EXÁMENES ---

class ExamConfig(BaseModel):
    student_id: str
    course_id: str
    # La dificultad se adapta, pero el tipo cognitivo viene del curso
    target_difficulty: ExamDifficulty = ExamDifficulty.MEDIUM
    topics_filter: Optional[List[str]] = None # "Solo quiero practicar Integrales"
    
class GeneratedQuestion(BaseModel):
    id: str
    question_latex: str # La pregunta renderizable
    options_latex: Optional[List[str]] = None
    correct_answer_latex: str
    explanation_step_by_step: str # Chain of thought
    source_block_id: str # Trazabilidad: ¿De qué examen salió esto?
    difficulty: ExamDifficulty

class Exam(BaseModel):
    id: str
    course_id: str
    student_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    questions: List[GeneratedQuestion]
    score: Optional[float] = None