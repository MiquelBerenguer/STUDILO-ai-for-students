import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

# IMPORTS DE DOMINIO (Tus entidades intactas)
from src.services.learning.domain.entities import (
    ExamConfig, Exam, GeneratedQuestion, 
    QuestionType, CognitiveType,
    NumericalValidation, CodeValidation, MultipleChoiceValidation,
    CodeTestCase, EngineeringBlock
)

# IMPORTS DE SERVICIOS
from src.services.ai.service import AIService
# IMPORTANTE: Ahora importamos desde la "Nueva Casa" en AI
from src.services.ai.prompts import PromptManager 

# IMPORTS DE LÓGICA (Tu Blueprint y Selectores intactos)
from src.services.learning.logic.content_selector import ContentSelector
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.blueprint import ExamBlueprintBuilder, ExamSlot

logger = logging.getLogger(__name__)

class ExamGenerator:
    def __init__(
        self,
        content_selector: ContentSelector,
        style_selector: StyleSelector,
        ai_service: AIService,
        blueprint_builder: ExamBlueprintBuilder
    ):
        # Todo esto sigue igual que antes
        self.content_selector = content_selector
        self.style_selector = style_selector
        self.ai_service = ai_service
        self.blueprint_builder = blueprint_builder

    async def generate_exam(self, config: ExamConfig) -> Exam:
        start_time = datetime.now()
        logger.info(f"🏗️  INICIANDO FACTORÍA DE EXAMEN: {config.course_id}")

        # 1. SCOPE & BLUEPRINT (INTACTO: Tu lógica de estructura sigue aquí)
        topics = await self.content_selector.get_available_topics(config)
        exam_slots = self.blueprint_builder.create_blueprint(config, topics)
        
        # 2. GENERACIÓN PARALELA
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
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return await self._process_slot_logic(slot, config)
            except Exception as e:
                logger.warning(f"⚠️ Reintento {attempt+1} para Slot {slot.topic_id}: {e}")
                if attempt == max_retries:
                    raise e

    async def _process_slot_logic(self, slot: ExamSlot, config: ExamConfig) -> GeneratedQuestion:
        # A. Contexto (RAG)
        chunks = await self.content_selector.fetch_context_for_slot(
            config.course_id, slot.topic_id
        )
        rag_context_text = "\n".join([f"- {c.latex_content}" for c in chunks])
        
        # B. Estilo
        pattern = await self.style_selector.select_best_pattern(
            course_id=config.course_id,
            domain="engineering",
            cognitive_needed=slot.cognitive_target,
            difficulty=slot.difficulty
        )

        # C. Determinar Tipo
        target_q_type = self._determine_question_type(slot, config)

        # D. Construcción del Prompt (AQUÍ ESTÁ EL CAMBIO LIMPIO)
        # En vez de tener el texto sucio aquí, llamamos a la "Nueva Casa"
        prompt = PromptManager.get_engineering_prompt(
            topic=slot.topic_id,
            difficulty=slot.difficulty,
            cognitive_type=slot.cognitive_target,
            points=getattr(slot, 'points', 1.0),
            rag_context=rag_context_text,
            question_type=target_q_type,
            style_instruction=pattern.reasoning_recipe if pattern else None
        )

        # E. Llamada AI
        ai_response = await self.ai_service.generate_json(
            prompt=prompt,
            model="gpt-4o-2024-08-06",
            temperature=0.2
        )

        # F. Mapeo (INTACTO: Tu lógica de validación sigue aquí)
        return self._map_json_to_domain(ai_response, slot, chunks, target_q_type)

    def _determine_question_type(self, slot: ExamSlot, config: ExamConfig) -> QuestionType:
        # Lógica original preservada
        if config.include_code_questions and slot.cognitive_target in [CognitiveType.COMPUTATIONAL, CognitiveType.DEBUGGING]:
            if "code" in slot.topic_id or "algorithm" in slot.topic_id:
                return QuestionType.CODE_EDITOR
        if slot.cognitive_target == CognitiveType.CONCEPTUAL:
            return QuestionType.MULTIPLE_CHOICE
        return QuestionType.NUMERIC_INPUT

    def _map_json_to_domain(self, data: Dict, slot: ExamSlot, chunks: List[EngineeringBlock], q_type: QuestionType) -> GeneratedQuestion:
        # Tu mapeo original preservado
        validation_rules = None
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
            statement_latex=data.get("statement_latex", "Error"),
            code_context=data.get("code_context"),
            cognitive_type=slot.cognitive_target,
            difficulty=slot.difficulty,
            question_type=q_type,
            source_block_id=chunks[0].id if chunks else "unknown",
            validation_rules=validation_rules,
            step_by_step_solution_latex=data.get("explanation", ""),
            hint=data.get("hint")
        )