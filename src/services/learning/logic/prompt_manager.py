import json
from enum import Enum
from typing import Optional, List
from src.services.learning.domain.entities import (
    CognitiveType, QuestionType, ExamDifficulty
)

class StudyPhase(str, Enum):
    ANALYSIS = "analysis"
    RECALL = "recall"
    VALIDATION = "validation"
    BUILDING = "building"

class PromptManager:
    """
    Gestor Central de Personalidad y Estrategia Pedagógica.
    Sincronizado estrictamente con src/services/learning/domain/entities.py
    """

    @staticmethod
    def _get_base_identity() -> str:
        return """
        ROL: Eres un Ingeniero Senior y Profesor Universitario ("El Mentor Ingeniero").
        TONO: Profesional, riguroso pero didáctico. Obsesionado con las unidades correctas y la notación precisa.
        """

    # =========================================================================
    # MÓDULO 2: ARQUITECTO DE EXÁMENES (Optimizado)
    # =========================================================================
    
    @staticmethod
    def _get_json_schema_instruction(q_type: QuestionType) -> str:
        """
        Define la estructura JSON exacta que el ExamGenerator necesita para mapear
        a las entidades Pydantic sin errores.
        """
        base_fields = """
            "statement_latex": "Enunciado del problema usando LaTeX para fórmulas ($...$).",
            "explanation": "Explicación detallada paso a paso (Chain of Thought).",
            "hint": "Pista sutil conceptual (sin dar la solución).",
        """

        if q_type == QuestionType.NUMERIC_INPUT:
            return f"""
            FORMATO JSON OBLIGATORIO (NUMÉRICO):
            {{
                {base_fields}
                "numeric_solution": 9.81,  // Float puro.
                "tolerance_percent": 2.0,  // Margen de error (ej: 2% para ingeniería).
                "units": ["m/s^2", "N/kg"] // Lista de unidades válidas en SI.
            }}
            """
        elif q_type == QuestionType.CODE_EDITOR:
            return f"""
            FORMATO JSON OBLIGATORIO (CÓDIGO):
            {{
                {base_fields}
                "code_context": "Firma de la función inicial (ej: def calcular_viga(l, q):)",
                "test_cases": [
                    {{
                        "input": "2.5, 100", // Argumentos de entrada como string
                        "output": "312.5",    // Resultado esperado
                        "hidden": false       // Visible para el alumno
                    }}
                ]
            }}
            """
        elif q_type == QuestionType.MULTIPLE_CHOICE:
            return f"""
            FORMATO JSON OBLIGATORIO (TEST):
            {{
                {base_fields}
                "options": ["Opción A", "Opción B", "Opción C", "Opción D"],
                "correct_option_index": 0 // Índice base-0 (0=A, 1=B...)
            }}
            """
        
        # Fallback para OPEN_TEXT u otros
        return f"""
        FORMATO JSON OBLIGATORIO:
        {{
            {base_fields}
        }}
        """

    @staticmethod
    def get_engineering_prompt(
        topic: str,
        difficulty: ExamDifficulty,
        cognitive_type: CognitiveType,
        points: float,
        rag_context: str,
        question_type: QuestionType,
        style_instruction: Optional[str] = None
    ) -> str:
        
        # 1. Obtener el esquema JSON alineado con entities.py
        json_instruction = PromptManager._get_json_schema_instruction(question_type)
        
        # 2. Instrucciones de Ingeniería Específicas
        engineering_guidelines = """
        REGLAS DE INGENIERÍA:
        1. RIGOR: Usa Sistema Internacional (SI) salvo que el contexto histórico pida otro.
        2. REALISMO: Los valores numéricos deben tener sentido físico (no masas negativas, no eficiencias > 100%).
        3. NOTACIÓN: Usa LaTeX para toda variable matemática. E.g., $\sigma = F/A$.
        """

        # 3. Lógica Cognitiva
        cognitive_instruction = ""
        if cognitive_type == CognitiveType.COMPUTATIONAL:
            cognitive_instruction = "El problema debe requerir cálculo numérico y aplicación de fórmulas."
        elif cognitive_type == CognitiveType.CONCEPTUAL:
            cognitive_instruction = "Evalúa la comprensión profunda de la teoría, no solo la memoria."
        elif cognitive_type == CognitiveType.DEBUGGING:
            cognitive_instruction = "Presenta un escenario con un fallo o error que el estudiante debe identificar."
        elif cognitive_type == CognitiveType.DESIGN_ANALYSIS:
            cognitive_instruction = "Pide analizar trade-offs o diseñar un sistema bajo restricciones."

        return f"""
        {PromptManager._get_base_identity()}
        
        TAREA: Generar una pregunta de examen de Ingeniería.
        TIPO: {question_type.value.upper()}
        TEMA: {topic}
        DIFICULTAD: {difficulty.value.upper()} ({points} puntos posibles)
        ENFOQUE COGNITIVO: {cognitive_type.value.upper()}
        
        {engineering_guidelines}
        
        {cognitive_instruction}
        
        CONTEXTO TÉCNICO (Fuente de Verdad - RAG):
        {rag_context}
        
        INSTRUCCIONES DE ESTILO:
        {style_instruction if style_instruction else "Usa un estilo académico estándar, directo y claro."}
        
        {json_instruction}
        
        IMPORTANTE: Devuelve SOLO el JSON válido. No añadas markdown ```json ... ``` ni texto extra.
        """