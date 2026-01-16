from pydantic import BaseModel, Field
from typing import List, Literal, Union, Dict, Any

# =============================================================================
# ESQUEMAS ROBUSTOS (Literal + Strict Config)
# =============================================================================

class TestCase(BaseModel):
    input_data: str = Field(..., description="Entrada del test")
    expected_output: str = Field(..., description="Salida esperada")
    is_hidden: bool = Field(..., description="Si es un test oculto")

class NumericContent(BaseModel):
    # USAMOS LITERAL: Seguridad total. Solo acepta esta cadena exacta.
    kind: Literal["numeric_input"] = Field("numeric_input", description="Tipo fijo")
    
    statement_latex: str = Field(..., description="Enunciado en LaTeX")
    explanation: str = Field(..., description="Explicación paso a paso")
    hint: Union[str, None] = Field(..., description="Pista breve (o null)")
    
    # Datos planos (Ya no están dentro de validation_rules)
    numeric_solution: float = Field(..., description="Solución numérica exacta")
    tolerance_percent: float = Field(..., description="Margen de error %")
    units: List[str] = Field(..., description="Lista de unidades permitidas")

class ChoiceContent(BaseModel):
    kind: Literal["multiple_choice"] = Field("multiple_choice", description="Tipo fijo")
    
    statement_latex: str = Field(..., description="Enunciado en LaTeX")
    explanation: str = Field(..., description="Explicación")
    hint: Union[str, None] = Field(..., description="Pista breve (o null)")
    
    options: List[str] = Field(..., min_items=2, description="Lista de opciones")
    correct_option_index: int = Field(..., description="Índice 0-based")

class CodeContent(BaseModel):
    kind: Literal["code_editor"] = Field("code_editor", description="Tipo fijo")
    
    statement_latex: str = Field(..., description="Enunciado en LaTeX")
    explanation: str = Field(..., description="Explicación")
    hint: Union[str, None] = Field(..., description="Pista breve (o null)")
    
    code_context: str = Field(..., description="Código inicial")
    test_cases: List[TestCase] = Field(..., description="Casos de prueba")

# Unión simple (Dejamos que Pydantic infiera el tipo por el campo 'kind')
QuestionContentVariant = Union[NumericContent, ChoiceContent, CodeContent]

class ReasoningQuestionResponse(BaseModel):
    chain_of_thought: str = Field(..., description="Razonamiento interno previo.")
    content: QuestionContentVariant