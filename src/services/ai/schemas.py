from __future__ import annotations
from typing import List, Union, Literal
from pydantic import BaseModel, Field

# Mantenemos tus imports de dominio
from src.services.learning.domain.entities import (
    ExamDifficulty, 
    QuestionType, 
    CognitiveType,
    Language
)

# ---------------------------------------------------------
# 1. REGLAS ESPECÍFICAS (Sin cambios, solo puras definiciones)
# ---------------------------------------------------------

class NumericRuleAI(BaseModel):
    correct_value: float
    tolerance_percentage: float = Field(..., description="Margen de error en % (0-100)")
    allowed_units: List[str] = Field(default_factory=list)

class ChoiceRuleAI(BaseModel):
    options: List[str] = Field(..., min_items=2)
    correct_index: int = Field(..., description="Índice 0-based de la opción correcta")

class CodeRuleAI(BaseModel):
    test_inputs: List[str]
    expected_outputs: List[str]

# ---------------------------------------------------------
# 2. DEFINICIÓN POLIMÓRFICA DE PREGUNTAS
# ---------------------------------------------------------

class BaseQuestionAI(BaseModel):
    """Campos comunes a todas las preguntas"""
    statement_latex: str = Field(..., description="Enunciado. Usa LaTeX ($...$) para matemáticas.")
    difficulty: ExamDifficulty
    cognitive_type: CognitiveType
    explanation: str = Field(..., description="Explicación paso a paso.")
    hint: str | None = None

# --- AQUI ESTÁ LA MAGIA ---
# Definimos una clase por cada tipo, forzando el 'question_type' con Literal

class NumericQuestionAI(BaseQuestionAI):
    question_type: Literal[QuestionType.NUMERIC_INPUT] = QuestionType.NUMERIC_INPUT
    numeric_rule: NumericRuleAI = Field(..., description="Reglas numéricas obligatorias")

class ChoiceQuestionAI(BaseQuestionAI):
    question_type: Literal[QuestionType.MULTIPLE_CHOICE] = QuestionType.MULTIPLE_CHOICE
    choice_rule: ChoiceRuleAI = Field(..., description="Opciones obligatorias")

class CodeQuestionAI(BaseQuestionAI):
    question_type: Literal[QuestionType.CODE_EDITOR] = QuestionType.CODE_EDITOR
    code_rule: CodeRuleAI = Field(..., description="Casos de prueba obligatorios")

class OpenQuestionAI(BaseQuestionAI):
    question_type: Literal[QuestionType.OPEN_TEXT] = QuestionType.OPEN_TEXT
    # No tiene reglas específicas, pero definimos la clase para ser explícitos

# Creamos la Unión que usará OpenAI para decidir qué estructura llenar
# IMPORTANTE: El orden no altera el producto, pero ayuda a la claridad.
AnyQuestionAI = Union[
    NumericQuestionAI, 
    ChoiceQuestionAI, 
    CodeQuestionAI, 
    OpenQuestionAI
]

# ---------------------------------------------------------
# 3. EL CEREBRO (Respuesta Raíz)
# ---------------------------------------------------------

class ReasoningExamResponse(BaseModel):
    chain_of_thought: str = Field(
        ..., 
        description="Tu proceso de razonamiento pedagógico antes de generar las preguntas."
    )
    # Aquí usamos la Unión. OpenAI detectará el campo 'question_type' (discriminator) automáticamente.
    questions: List[AnyQuestionAI]