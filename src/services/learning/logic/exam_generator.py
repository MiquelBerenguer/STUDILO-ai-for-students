import logging
import asyncio
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

# Imports de Entidades
from src.services.learning.domain.entities import (
    ExamConfig, Exam, GeneratedQuestion, ExamDifficulty, 
    CognitiveType, PedagogicalPattern, QuestionType,
    NumericalValidation, CodeValidation, MultipleChoiceValidation,
    CodeTestCase, EngineeringBlock
)

# Imports de Lógica (Asumimos que existen en tu proyecto)
from src.services.learning.logic.content_selector import ContentSelector
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.blueprint import ExamBlueprintBuilder, ExamSlot
from src.services.ai.client import AIService

logger = logging.getLogger(__name__)

class ExamGenerator:
    def __init__(
        self,
        content_selector: ContentSelector,
        style_selector: StyleSelector,
        ai_service: AIService,
        blueprint_builder: ExamBlueprintBuilder
    ):
        self.content_selector = content_selector
        self.style_selector = style_selector
        self.ai_service = ai_service
        self.blueprint_builder = blueprint_builder

    async def generate_exam(self, config: ExamConfig) -> Exam:
        start_time = datetime.now()
        logger.info(f"🏗️  INICIANDO FACTORÍA DE EXAMEN: {config.course_id}")

        # 1. SCOPE & BLUEPRINT (El Plano)
        topics = await self.content_selector.get_available_topics(config)
        exam_slots = self.blueprint_builder.create_blueprint(config, topics)
        
        # 2. GENERACIÓN PARALELA (Rendimiento)
        # Lanzamos todas las preguntas a la vez al LLM
        tasks = [
            self._generate_single_question_safely(slot, config) 
            for slot in exam_slots
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. FILTRADO Y VALIDACIÓN
        valid_questions = []
        for i, result in enumerate(results):
            if isinstance(result, GeneratedQuestion):
                valid_questions.append(result)
            else:
                logger.error(f"❌ Fallo generando Slot {i}: {result}")
        
        # Calidad mínima: Si falla más del 20% de preguntas, abortamos
        if len(valid_questions) < len(exam_slots) * 0.8:
            raise Exception("No se pudo generar un examen con la calidad mínima requerida.")

        logger.info(f"✅ Examen generado en {(datetime.now() - start_time).seconds}s con {len(valid_questions)} preguntas.")
        
        return Exam(
            config=config,
            questions=valid_questions,
            created_at=datetime.utcnow(),
            status="ready"
        )

    async def _generate_single_question_safely(self, slot: ExamSlot, config: ExamConfig) -> GeneratedQuestion:
        """Wrapper con reintentos para robustez."""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return await self._process_slot_logic(slot, config)
            except Exception as e:
                logger.warning(f"⚠️ Reintento {attempt+1} para Slot {slot.slot_index}: {e}")
                if attempt == max_retries:
                    raise e

    async def _process_slot_logic(self, slot: ExamSlot, config: ExamConfig) -> GeneratedQuestion:
        # A. Contexto (RAG)
        chunks = await self.content_selector.fetch_context_for_slot(
            config.course_id, slot.topic_id
        )
        
        # B. Estilo (Pattern)
        pattern = await self.style_selector.select_best_pattern(
            course_id=config.course_id,
            domain="engineering",
            cognitive_needed=slot.cognitive_target,
            difficulty=slot.difficulty
        )

        # C. Determinar Tipo y Prompt
        target_q_type = self._determine_question_type(slot, config)
        prompt = self._build_strict_prompt(slot, chunks, pattern, target_q_type)

        # D. Llamada AI
        ai_response = await self.ai_service.generate_json(
            prompt=prompt,
            model="gpt-4-turbo",
            temperature=0.4
        )

        # E. Mapeo a Entidad
        return self._map_json_to_domain(ai_response, slot, chunks, target_q_type)

    def _determine_question_type(self, slot: ExamSlot, config: ExamConfig) -> QuestionType:
        """Lógica determinista para elegir formato."""
        # Si es programación/debugging, forzamos editor de código
        if config.include_code_questions and slot.cognitive_target in [CognitiveType.COMPUTATIONAL, CognitiveType.DEBUGGING]:
            if "code" in slot.topic_id or "algorithm" in slot.topic_id:
                return QuestionType.CODE_EDITOR
        
        # Si es conceptual, test multirespuesta
        if slot.cognitive_target == CognitiveType.CONCEPTUAL:
            return QuestionType.MULTIPLE_CHOICE
        
        # Por defecto ingeniería: Numérico
        return QuestionType.NUMERIC_INPUT

    def _build_strict_prompt(self, slot, chunks, pattern, q_type) -> str:
        # Aquí inyectamos el esquema JSON específico según el tipo de pregunta
        json_schema_instruction = ""
        
        if q_type == QuestionType.NUMERIC_INPUT:
            json_schema_instruction = """
            "numeric_solution": 123.45 (float),
            "tolerance_percent": 5.0 (float),
            "units": ["m/s", "km/h"] (list string)
            """
        elif q_type == QuestionType.CODE_EDITOR:
            json_schema_instruction = """
            "test_cases": [
                {"input": "arg1", "output": "expected1", "hidden": false},
                {"input": "arg2", "output": "expected2", "hidden": true}
            ]
            """
        elif q_type == QuestionType.MULTIPLE_CHOICE:
            json_schema_instruction = """
            "options": ["Opción A", "Opción B", "Opción C", "Opción D"],
            "correct_option_index": 0 (int, 0-based)
            """

        context_text = "\n".join([f"- {c.latex_content}" for c in chunks])

        return f"""
        ROL: Profesor de Ingeniería Experto.
        TAREA: Generar 1 pregunta de examen.
        TEMA: {slot.topic_id}
        DIFICULTAD: {slot.difficulty.value}
        TIPO OBJETIVO: {q_type.value}

        CONTEXTO (Fuente de Verdad):
        {context_text}

        ESTRUCTURA JSON OBLIGATORIA:
        {{
            "statement_latex": "Enunciado claro usando LaTeX ($...$).",
            "code_context": "Código inicial si es necesario, o null.",
            "explanation": "Explicación paso a paso (Chain of Thought).",
            "hint": "Pista sutil.",
            {json_schema_instruction}
        }}
        """

    def _map_json_to_domain(self, data: Dict, slot: ExamSlot, chunks: List[EngineeringBlock], q_type: QuestionType) -> GeneratedQuestion:
        validation_rules = None
        
        # Factory de validación
        if q_type == QuestionType.NUMERIC_INPUT:
            validation_rules = NumericalValidation(
                correct_value=float(data.get("numeric_solution", 0.0)),
                tolerance_percentage=float(data.get("tolerance_percent", 5.0)),
                allowed_units=data.get("units", [])
            )
        elif q_type == QuestionType.CODE_EDITOR:
            tcs = [CodeTestCase(input_data=tc["input"], expected_output=tc["output"], is_hidden=tc.get("hidden", False)) 
                   for tc in data.get("test_cases", [])]
            validation_rules = CodeValidation(test_cases=tcs)
        elif q_type == QuestionType.MULTIPLE_CHOICE:
            validation_rules = MultipleChoiceValidation(
                options=data.get("options", []),
                correct_index=int(data.get("correct_option_index", 0))
            )

        return GeneratedQuestion(
            statement_latex=data["statement_latex"],
            code_context=data.get("code_context"),
            cognitive_type=slot.cognitive_target,
            difficulty=slot.difficulty,
            question_type=q_type,
            source_block_id=chunks[0].id if chunks else "unknown",
            validation_rules=validation_rules,
            step_by_step_solution_latex=data["explanation"],
            hint=data.get("hint")
        )