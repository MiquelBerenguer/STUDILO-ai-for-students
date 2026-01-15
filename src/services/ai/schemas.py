from typing import List, Optional
from pydantic import BaseModel, Field, model_validator, ValidationInfo

# IMPORTANTE: Importamos la "Verdad" del dominio. No la redefinimos.
from src.services.learning.domain.entities import (
    ExamDifficulty, 
    QuestionType, 
    CognitiveType,
    Language
)

# --- Sub-esquemas de Reglas (Input para la IA) ---

class NumericRuleAI(BaseModel):
    correct_value: float
    tolerance_percentage: float = Field(..., ge=0.0, le=100.0, description="Margen de error aceptable en %")
    allowed_units: List[str] = Field(default_factory=list)

class ChoiceRuleAI(BaseModel):
    options: List[str] = Field(..., min_items=2, description="Opciones de respuesta")
    correct_index: int = Field(..., description="Índice de la opción correcta (0-based)")

    @model_validator(mode='after')
    def validate_index_bounds(self) -> 'ChoiceRuleAI':
        if not (0 <= self.correct_index < len(self.options)):
            raise ValueError(f"correct_index ({self.correct_index}) fuera de rango para {len(self.options)} opciones.")
        return self

class CodeRuleAI(BaseModel):
    # Simplificamos para la IA: listas paralelas son más fáciles de generar que listas de objetos
    test_inputs: List[str]
    expected_outputs: List[str]

    @model_validator(mode='after')
    def validate_pairs(self) -> 'CodeRuleAI':
        if len(self.test_inputs) != len(self.expected_outputs):
            raise ValueError("El número de inputs debe coincidir con el de outputs.")
        return self

# --- El Objeto de Pregunta (Validado) ---

class QuestionAI(BaseModel):
    """
    Representación de la pregunta tal como la genera la IA.
    Luego se mapeará a la entidad de dominio 'GeneratedQuestion'.
    """
    statement_latex: str = Field(..., description="Enunciado. Usa LaTeX ($...$) para matemáticas.")
    difficulty: ExamDifficulty
    cognitive_type: CognitiveType
    question_type: QuestionType
    
    explanation: str = Field(..., description="Explicación pedagógica de la solución.")
    hint: Optional[str] = None
    
    # Contenedores Opcionales (Estrategia del Usuario)
    numeric_rule: Optional[NumericRuleAI] = None
    choice_rule: Optional[ChoiceRuleAI] = None
    code_rule: Optional[CodeRuleAI] = None

    @model_validator(mode='after')
    def enforce_type_consistency(self) -> 'QuestionAI':
        """
        Tu lógica de validación maestra: asegura que el tipo coincida con la regla.
        """
        q_type = self.question_type
        
        # Mapeo: Tipo -> (Campo Obligatorio, Campos Prohibidos)
        rules_map = {
            QuestionType.NUMERIC_INPUT: ('numeric_rule', ['choice_rule', 'code_rule']),
            QuestionType.MULTIPLE_CHOICE: ('choice_rule', ['numeric_rule', 'code_rule']),
            QuestionType.CODE_EDITOR: ('code_rule', ['numeric_rule', 'choice_rule']),
            QuestionType.OPEN_TEXT: (None, ['numeric_rule', 'choice_rule', 'code_rule'])
        }

        if q_type not in rules_map:
            return self 

        required_field, forbidden_fields = rules_map[q_type]

        # 1. Verificar requerido
        if required_field and getattr(self, required_field) is None:
            raise ValueError(f"Para {q_type.value}, el campo '{required_field}' es obligatorio.")

        # 2. Verificar prohibidos (Limpieza)
        for field_name in forbidden_fields:
            if getattr(self, field_name) is not None:
                raise ValueError(f"Para {q_type.value}, el campo '{field_name}' debe ser NULL.")

        return self

# --- EL CEREBRO (Wrapper Chain of Thought) ---

class ReasoningExamResponse(BaseModel):
    """
    Respuesta Raíz que esperamos de GPT-4o.
    Incluye el pensamiento global antes de las preguntas.
    """
    chain_of_thought: str = Field(
        ..., 
        description=(
            "PLANIFICACIÓN PEDAGÓGICA INTERNA. "
            "1. Analiza el perfil del estudiante y los temas solicitados. "
            "2. Diseña una progresión de dificultad (Scaffolding). "
            "3. Verifica que no se repitan conceptos. "
            "Este campo es tu 'borrador' antes de generar el JSON final."
        )
    )
    questions: List[QuestionAI] = Field(..., description="Lista de preguntas generadas y validadas.")