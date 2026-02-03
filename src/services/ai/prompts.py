from typing import Optional, Union, Any
from src.services.learning.domain.entities import (
    ExamDifficulty, 
    QuestionType, 
    CognitiveType, 
    Language
)

class PromptManager:
    """
    CEREBRO CENTRALIZADO DE PROMPTS (MASTER VERSION).
    Combina:
    - Pilar 1: Generador (Examiner)
    - Pilar 2: Tutor (Professor)
    - Pilar 3: Corrector (Grader)
    """

    @staticmethod
    def _safe_val(item: Any) -> str:
        """Helper para extraer valor de Enum o String de forma segura."""
        if hasattr(item, 'value'):
            return str(item.value)
        return str(item)

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
    def _get_content_guidelines(q_type: Union[QuestionType, str]) -> str:
        q_val = PromptManager._safe_val(q_type)
        numeric_val = PromptManager._safe_val(QuestionType.NUMERIC_INPUT)
        code_val = PromptManager._safe_val(QuestionType.CODE_EDITOR)
        choice_val = PromptManager._safe_val(QuestionType.MULTIPLE_CHOICE)
        
        if q_val == numeric_val:
            return "- NUMÉRICO: El problema debe tener solución única. Calcula la solución paso a paso internamente. Define tolerancia (2-5%) y unidades SI."
        elif q_val == code_val:
            return "- CÓDIGO: Proporciona firma de función clara. Los tests deben cubrir casos borde (nulls, ceros, negativos)."
        elif q_val == choice_val:
            return "- TEST: Solo 1 correcta. Los distractores deben basarse en errores conceptuales comunes."
        return ""

    @staticmethod
    def _get_structure_hint(q_type: Union[QuestionType, str]) -> str:
        base = "Campos requeridos: statement_latex, explanation, hint."
        q_val = PromptManager._safe_val(q_type)
        numeric_val = PromptManager._safe_val(QuestionType.NUMERIC_INPUT)
        code_val = PromptManager._safe_val(QuestionType.CODE_EDITOR)
        choice_val = PromptManager._safe_val(QuestionType.MULTIPLE_CHOICE)
        
        if q_val == numeric_val:
            return f"{base} Específicos: 'numeric_solution', 'tolerance_percent', 'units'."
        elif q_val == code_val:
            return f"{base} Específicos: 'code_context', 'test_cases' (input/output/hidden)."
        elif q_val == choice_val:
            return f"{base} Específicos: 'options', 'correct_option_index' (0-based)."
        return base

    @staticmethod
    def get_engineering_prompt(
        topic: str,
        difficulty: Union[ExamDifficulty, str],
        cognitive_type: Union[CognitiveType, str],
        points: float,
        rag_context: str,
        question_type: Union[QuestionType, str],
        style_instruction: Optional[str] = None
    ) -> str:
        
        content_guidelines = PromptManager._get_content_guidelines(question_type)
        structure_hint = PromptManager._get_structure_hint(question_type)
        
        diff_str = PromptManager._safe_val(difficulty).upper()
        type_str = PromptManager._safe_val(question_type).upper()
        cog_str = PromptManager._safe_val(cognitive_type).upper()
        
        return f"""
        {PromptManager._get_base_identity()}
        
        TAREA: Diseñar 1 pregunta de examen de Ingeniería.
        
        METADATOS:
        - TEMA: {topic}
        - DIFICULTAD: {diff_str} (Valor: {points} pts)
        - TIPO: {type_str}
        - COGNICIÓN: {cog_str}
        
        FUENTE DE VERDAD (RAG):
        \"\"\"
        {rag_context}
        \"\"\"
        
        INSTRUCCIONES DE RAZONAMIENTO (CHAIN OF THOUGHT):
        1. Tu salida tiene un campo 'chain_of_thought'. ÚSALO PRIMERO.
        2. Pasos obligatorios: Verificar cobertura del RAG, Resolver tú mismo, Justificar distractores.
        
        DIRECTRICES DE CALIDAD:
        {content_guidelines}
        
        RECORDATORIO DE CAMPOS JSON:
        {structure_hint}
        
        ESTILO:
        {style_instruction if style_instruction else "Académico, directo."}
        
        IMPORTANTE: Genera estrictamente el objeto JSON solicitado.
        """

    # =========================================================================
    # PILAR 2: CHATBOT TUTOR (The Professor)
    # =========================================================================

    @staticmethod
    def get_tutor_system_prompt(language: Union[Language, str]) -> str:
        lang_val = PromptManager._safe_val(language)
        es_val = PromptManager._safe_val(Language.ES)
        lang_instr = "Habla en Español." if lang_val == es_val else "Speak in English."
        
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

    # =========================================================================
    # PILAR 3: EL CORRECTOR (The Judge)
    # =========================================================================
    
    @staticmethod
    def get_grader_system_prompt() -> str:
        return """
        ROL: Eres un Corrector de Exámenes de Ingeniería ("The Grader").
        TONO: Objetivo, analítico, pero pedagógico.

        TU MISIÓN:
        Evaluar si un estudiante merece PUNTOS PARCIALES en una pregunta numérica fallida, basándote en su procedimiento escrito.

        MATRIZ DE PUNTUACIÓN (LÓGICA DE NEGOCIO):
        - A (80-90%): Procedimiento impecable, fórmula correcta, error aritmético simple al final.
        - B (50-60%): Planteamiento correcto, pero error en conversión de unidades o constantes.
        - C (20-30%): Intuyó el concepto físico correcto, pero erró en la fórmula base.
        - D (0%): Razonamiento incoherente, fórmula inventada, o texto vacío.

        SALIDA:
        Devuelve SOLO un JSON válido conforme al schema solicitado.
        """

    @staticmethod
    def build_grader_user_prompt(question_text: str, correct_val: str, student_val: str, student_text: str) -> str:
        return f"""
        --- PREGUNTA ---
        {question_text}

        --- SOLUCIÓN OFICIAL ---
        {correct_val}

        --- INTENTO DEL ESTUDIANTE ---
        Valor enviado: {student_val}
        Procedimiento:
        \"\"\"
        {student_text}
        \"\"\"

        --- TAREA ---
        1. Analiza el procedimiento.
        2. Clasifica el error según la Matriz.
        3. Calcula 'adjusted_score_percentage'.
        4. Genera feedback constructivo explicando DÓNDE falló.
        """