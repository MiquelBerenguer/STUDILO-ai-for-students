from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime

# --- 1. ENUMS (Tus 4 Tipos Sagrados) ---

class CognitiveType(str, Enum):
    # Matemáticas, Física, Programación
    PROCEDURAL = "procedural"       
    # Historia, Biología, Derecho
    DECLARATIVE = "declarative"     
    # Filosofía, Literatura (Análisis Crítico)
    INTERPRETATIVE = "interpretative" 
    # Economía, Sociología (Relaciones Abstractas)
    CONCEPTUAL = "conceptual"       

class ExamDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class PatternScope(str, Enum):
    GLOBAL = "global"
    DOMAIN = "domain"
    COURSE = "course"

# --- 2. ENTIDADES CORE ---

class ExamConfig(BaseModel):
    student_id: str
    course_id: str
    # AÑADIDO: El curso dicta el tipo, no la dificultad.
    course_cognitive_type: CognitiveType 
    
    num_questions: int = 10
    difficulty: ExamDifficulty = ExamDifficulty.MEDIUM
    topics: List[str] = []
    
class GeneratedQuestion(BaseModel):
    question_text: str
    options: Optional[List[str]] = None
    correct_answer: str
    explanation: str
    source_chunk_id: str
    used_pattern_id: Optional[str] = None

class Exam(BaseModel):
    id: str
    course_id: str
    student_id: str
    created_at: datetime
    questions: List[GeneratedQuestion]
    config_snapshot: ExamConfig
    ai_model_used: str

class PedagogicalPattern(BaseModel):
    id: str
    scope: PatternScope
    target_id: Optional[str]
    cognitive_type: CognitiveType
    difficulty: ExamDifficulty
    reasoning_recipe: str
    original_question: Optional[str]