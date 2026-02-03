from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- INPUT (Lo que llega del API) ---
class SolverRequest(BaseModel):
    question: str
    user_id: str
    conversation_history: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Historial previo [{'role': 'user', 'content': '...'}, ...]"
    )

# --- OUTPUT COMPONENTS (Lo que devuelve la IA) ---
class SourceReference(BaseModel):
    doc_name: str
    page_number: Optional[int] = None
    snippet: str
    relevance: float

class SolverResponse(BaseModel):
    """
    Estructura cognitiva del TutorIA.
    Diseñada para obligar a la IA a seguir la metodología pedagógica.
    """
    # 1. Reflexión interna (Ayuda a la IA a centrarse)
    thought_process: str = Field(..., description="Breve análisis interno: ¿Qué sabe el alumno? ¿Qué le falta?")

    # 2. La Explicación (Tu técnica)
    explanation_markdown: str = Field(..., description="La explicación conceptual. Usa LaTeX ($...$) para fórmulas y **negritas** para énfasis.")
    
    # 3. El Ejemplo (Requisito clave)
    concrete_example: str = Field(..., description="Un ejemplo práctico de ingeniería o analogía del mundo real que ilustre el concepto.")
    
    # 4. El Freno (Stop & Check)
    verification_question: str = Field(..., description="Una pregunta corta y directa para validar que el alumno entendió antes de seguir.")
    
    # 5. Fuente usada (Flag)
    used_general_knowledge: bool = Field(..., description="True si la respuesta se basó en conocimiento general por falta de apuntes.")
    
    # 6. Referencias (Se llenan en el servicio, no la IA)
    sources: List[SourceReference] = Field(default_factory=list)