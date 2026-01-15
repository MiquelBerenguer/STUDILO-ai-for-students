from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union, Dict, Any

# =============================================================================
# ESQUEMAS INTERNOS DE INTELIGENCIA ARTIFICIAL (Structured Outputs)
# =============================================================================

# NOTA DE INGENIERÍA: Usamos strings puros ("raw strings") en los Literals.
# NO usamos Enums aquí porque Pydantic genera esquemas 'const' que OpenAI rechaza.
# OpenAI necesita ver 'type: string' y 'enum: [...]'.

class NumericContent(BaseModel):
    # CORRECCIÓN CRÍTICA: String literal directo sin Enum
    kind: Literal["numeric_input"]
    
    statement_latex: str = Field(..., description="Enunciado del problema en LaTeX")
    explanation: str = Field(..., description="Explicación paso a paso")
    hint: Optional[str] = Field(None, description="Pista breve")
    
    # Campos OBLIGATORIOS
    numeric_solution: float
    tolerance_percent: float
    units: List[str]

class ChoiceContent(BaseModel):
    # CORRECCIÓN CRÍTICA: String literal directo sin Enum
    kind: Literal["multiple_choice"]
    
    statement_latex: str = Field(..., description="Enunciado del problema en LaTeX")
    explanation: str = Field(..., description="Explicación de por qué es la correcta")
    hint: Optional[str] = None
    
    # Campos OBLIGATORIOS
    options: List[str] = Field(..., min_items=2, description="Lista de opciones")
    correct_option_index: int = Field(..., description="Índice 0-based de la correcta")

class CodeContent(BaseModel):
    # CORRECCIÓN CRÍTICA: String literal directo sin Enum
    kind: Literal["code_editor"]
    
    statement_latex: str = Field(..., description="Enunciado del problema en LaTeX")
    explanation: str = Field(..., description="Explicación de la solución")
    hint: Optional[str] = None
    
    # Campos OBLIGATORIOS
    code_context: str = Field(..., description="Código inicial o firma de la función")
    test_cases: List[Dict[str, Any]] = Field(..., description="Lista de inputs/outputs para tests")

# --- Unión Discriminada ---
# Pydantic usará el campo 'kind' para saber qué esquema validar
QuestionContentVariant = Union[NumericContent, ChoiceContent, CodeContent]

class ReasoningQuestionResponse(BaseModel):
    chain_of_thought: str = Field(..., description="Razonamiento interno previo. ÚSALO para calcular y validar antes de responder.")
    content: QuestionContentVariant