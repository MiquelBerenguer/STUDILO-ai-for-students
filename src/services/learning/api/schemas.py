from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict
from datetime import date
from src.services.learning.domain.entities import ExamDifficulty, CognitiveType
from typing import List, Optional, Literal
from pydantic import BaseModel

# --- INPUTS ---

class CreateExamRequest(BaseModel):
    student_id: str
    course_id: str
    
    # Mantenemos tu validador inteligente
    difficulty: str = Field(default="medium") 
    num_questions: int = Field(default=5, ge=1, le=50)

    @field_validator('difficulty')
    def normalize_difficulty(cls, v):
        if isinstance(v, ExamDifficulty):
            return v
            
        v_str = str(v).lower().strip()
        
        mapping = {
            # Mapeos a FUNDAMENTAL (Tu equivalente a Easy)
            "facil": ExamDifficulty.FUNDAMENTAL,
            "easy": ExamDifficulty.FUNDAMENTAL,
            "fundamental": ExamDifficulty.FUNDAMENTAL,
            "beginner": ExamDifficulty.FUNDAMENTAL,
            
            # Mapeos a APPLIED (Tu equivalente a Medium)
            "medio": ExamDifficulty.APPLIED,
            "medium": ExamDifficulty.APPLIED,
            "applied": ExamDifficulty.APPLIED,
            "intermedio": ExamDifficulty.APPLIED,
            
            # Mapeos a COMPLEX (Tu equivalente a Hard)
            "dificil": ExamDifficulty.COMPLEX,
            "hard": ExamDifficulty.COMPLEX,
            "complex": ExamDifficulty.COMPLEX,
            "avanzado": ExamDifficulty.COMPLEX,
            
            # Mapeos especiales
            "gatekeeper": ExamDifficulty.GATEKEEPER
        }
        
        # Fallback seguro: Si no entiende, por defecto APPLIED (Nivel medio)
        return mapping.get(v_str, ExamDifficulty.APPLIED)

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

# Estructura de un mensaje individual
class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

# Entrada del Chat
class ChatRequest(BaseModel):
    message: str
    # IDs de archivos para RAG (Retrieval Augmented Generation)
    context_files: List[str] = [] 
    # El cliente mantiene el estado y lo envía cada vez (Stateless Server)
    conversation_history: List[Message] = [] 
    course_context: Optional[str] = None

# Salida del Chat
class ChatResponse(BaseModel):
    response: str
    methodology_step: str 
    sources: List[str] = []


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    download_url: Optional[str] = None