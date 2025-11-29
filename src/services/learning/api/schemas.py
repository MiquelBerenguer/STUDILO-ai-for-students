from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict
from datetime import date
from src.services.learning.domain.entities import ExamDifficulty, CognitiveType

# --- INPUTS ---

class CreateExamRequest(BaseModel):
    student_id: str
    course_id: str
    
    # Mantenemos tu validador inteligente
    difficulty: str = Field(default="medium") 
    num_questions: int = Field(default=5, ge=1, le=50)

    @field_validator('difficulty')
    def normalize_difficulty(cls, v):
        mapping = {
            "facil": ExamDifficulty.EASY,
            "easy": ExamDifficulty.EASY,
            "medio": ExamDifficulty.MEDIUM,
            "medium": ExamDifficulty.MEDIUM,
            "dificil": ExamDifficulty.HARD,
            "hard": ExamDifficulty.HARD,
        }
        return mapping.get(v.lower().strip(), ExamDifficulty.MEDIUM)

# Inputs para el Estilo (Nuevo Endpoint que añadimos antes)
class StyleRequest(BaseModel):
    course_id: str
    domain: str
    cognitive_type: CognitiveType
    difficulty: ExamDifficulty

# Inputs para el Planner
class PlanExamInput(BaseModel):
    id: str
    name: str
    exam_date: date
    difficulty_level: int
    topics_count: int = 1

class CreatePlanRequest(BaseModel):
    student_id: str
    exams: List[PlanExamInput]
    availability_slots: Dict[str, int] # "2023-10-20": 120
    force_include_ids: List[str] = []

# --- OUTPUTS ---

class ExamResponse(BaseModel):
    exam_id: str
    status: str = "generated"
    # Aquí podríamos devolver el examen completo si quisiéramos

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