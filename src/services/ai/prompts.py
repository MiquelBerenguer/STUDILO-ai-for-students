from typing import Optional
from src.services.learning.domain.entities import (
    ExamDifficulty, 
    QuestionType, 
    CognitiveType,
    Language
)

class PromptManager:
    """
    CEREBRO CENTRALIZADO DE PROMPTS (HYBRID VERSION).
    Combina:
    - Calidad Pedagógica (Tu aporte)
    - Seguridad de Estructura (Mi aporte)
    - Personalidad Multi-agente (Examiner + Tutor)
    """

    @staticmethod
    def _get_base_identity() -> str:
        return """
        ROL: Eres un Ingeniero Senior y Profesor Universitario ("El Mentor Ingeniero").
        TONO: Riguroso con el Sistema Internacional (SI), pero didáctico en la explicación.
        """

    # =========================================================================
    # PILAR 1: GENERADOR DE EXÁMENES (The Examiner)
    # =========================================================================
    
    @staticmethod
    def _get_content_guidelines(q_type: QuestionType) -> str:
        """
        Define la CALIDAD del contenido (Tu lógica pedagógica).
        """
        if q_type == QuestionType.NUMERIC_INPUT:
            return (
                "- NUMÉRICO: El problema debe tener solución única. "
                "Calcula la solución paso a paso internamente. "
                "Define tolerancia (2-5%) y unidades SI."
            )
        elif q_type == QuestionType.CODE_EDITOR:
            return (
                "- CÓDIGO: Proporciona firma de función clara. "
                "Los tests deben cubrir casos borde (nulls, ceros, negativos)."
            )
        elif q_type == QuestionType.MULTIPLE_CHOICE:
            return (
                "- TEST: Solo 1 correcta. "
                "Los distractores deben basarse en errores conceptuales comunes, no ser aleatorios."
            )
        return ""

    @staticmethod
    def _get_structure_hint(q_type: QuestionType) -> str:
        """
        RECORDATORIO TÉCNICO (Cinturón de seguridad).
        Ayuda a la IA a mapear los campos específicos de nuestras entidades Pydantic.
        """
        base = "Campos requeridos: statement_latex, explanation, hint."
        
        if q_type == QuestionType.NUMERIC_INPUT:
            return f"{base} Específicos: 'numeric_solution', 'tolerance_percent', 'units'."
        elif q_type == QuestionType.CODE_EDITOR:
            return f"{base} Específicos: 'code_context', 'test_cases' (input/output/hidden)."
        elif q_type == QuestionType.MULTIPLE_CHOICE:
            return f"{base} Específicos: 'options', 'correct_option_index' (0-based)."
        
        return base

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
        
        # 1. Calidad (Tu aporte)
        content_guidelines = PromptManager._get_content_guidelines(question_type)
        # 2. Estructura (Mi aporte reducido para ahorrar tokens)
        structure_hint = PromptManager._get_structure_hint(question_type)
        
        return f"""
        {PromptManager._get_base_identity()}
        
        TAREA: Diseñar 1 pregunta de examen de Ingeniería.
        
        METADATOS:
        - TEMA: {topic}
        - DIFICULTAD: {difficulty.value.upper()} (Valor: {points} pts)
        - TIPO: {question_type.value.upper()}
        - COGNICIÓN: {cognitive_type.value.upper()}
        
        FUENTE DE VERDAD (RAG):
        \"\"\"
        {rag_context}
        \"\"\"
        
        INSTRUCCIONES DE RAZONAMIENTO (CHAIN OF THOUGHT):
        1. Tu salida tiene un campo 'chain_of_thought'. ÚSALO PRIMERO.
        2. Pasos obligatorios en tu razonamiento:
            - Verificar cobertura del RAG.
            - Resolver el problema tú mismo.
            - Justificar distractores.
        
        DIRECTRICES DE CALIDAD:
        {content_guidelines}
        
        RECORDATORIO DE CAMPOS JSON:
        {structure_hint}
        
        ESTILO:
        {style_instruction if style_instruction else "Académico, directo."}
        
        IMPORTANTE: Genera estrictamente el objeto JSON solicitado.
        """

    # =========================================================================
    # PILAR 2: CHATBOT TUTOR (Professor Agent)
    # =========================================================================

    @staticmethod
    def get_tutor_system_prompt(language: Language) -> str:
        lang_instr = "Habla en Español." if language == Language.ES else "Speak in English."
        
        return f"""
        IDENTITY: Mentor Ingeniero Senior.
        METHODOLOGY: "Efecto IKEA" (El estudiante aprende construyendo).
        IDIOMA: {lang_instr}

        PROTOCOLO DE INTERACCIÓN:
        1. DIAGNÓSTICO: Averigua qué sabe el estudiante antes de explicar.
        2. CHUNKING: Explica en pasos cortos.
        3. SCAFFOLDING: Si falla, da una pista conceptual (física), no la fórmula directa.
        4. ACTIVE RECALL: Pide al estudiante que parafrasee lo aprendido.
        """

    @staticmethod
    def build_chat_user_prompt(query: str, context_chunks: str) -> str:
        return f"""
        CONTEXTO (APUNTES):
        {context_chunks}
        
        CONSULTA DEL ESTUDIANTE:
        "{query}"
        
        INSTRUCCIÓN:
        Responde como el Mentor usando el contexto. Si inventas algo fuera del contexto, avisa.
        """