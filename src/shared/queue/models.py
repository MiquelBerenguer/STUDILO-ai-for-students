from uuid import UUID
from enum import Enum
from pydantic import BaseModel

# 1. Tipos Cognitivos estrictos
class CognitiveType(str, Enum):
    PROCEDURAL = "procedural"
    DECLARATIVE = "declarative"
    INTERPRETATIVE = "interpretative"
    CONCEPTUAL = "conceptual"

# 2. El mensaje que viaja por la cola
class PDFGenerationJob(BaseModel):
    task_id: UUID           # ID de rastreo
    user_id: UUID           # Quién lo pide
    exam_id: UUID           # Qué examen generar
    cognitive_type: CognitiveType  # Estilo del PDF
    include_solutions: bool = False

    class Config:
        use_enum_values = True