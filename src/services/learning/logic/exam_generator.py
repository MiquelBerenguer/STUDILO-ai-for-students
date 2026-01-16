import logging
import asyncio
from datetime import datetime
from typing import List, Any

# --- IMPORTS DE DOMINIO ---
from src.services.learning.domain.entities import (
    ExamConfig, Exam, GeneratedQuestion, 
    QuestionType, CognitiveType,
    NumericalValidation, CodeValidation, MultipleChoiceValidation,
    CodeTestCase, EngineeringBlock, ExamDifficulty
)

# --- IMPORTS DE INFRAESTRUCTURA (NUEVO CEREBRO) ---
from src.services.ai.service import AIService
# Importamos los esquemas de la IA para poder leer su respuesta
from src.services.ai.schemas import (
    NumericQuestionAI, ChoiceQuestionAI, CodeQuestionAI, OpenQuestionAI,
    ReasoningExamResponse
)

# --- IMPORTS DE LÓGICA ---
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
        self.content_selector = content_selector
        self.style_selector = style_selector
        self.ai_service = ai_service
        self.blueprint_builder = blueprint_builder

    async def generate_exam(self, config: ExamConfig) -> Exam:
        start_time = datetime.now()
        logger.info(f"🏗️  INICIANDO FACTORÍA DE EXAMEN: {config.course_id}")

        # 1. SCOPE & BLUEPRINT
        topics = await self.content_selector.get_available_topics(config)
        exam_slots = self.blueprint_builder.create_blueprint(config, topics)
        
        # 2. GENERACIÓN PARALELA
        logger.info(f"🚀 Lanzando generación de {len(exam_slots)} preguntas en paralelo...")
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
        
        # Umbral de calidad: Si fallan demasiadas, abortamos.
        if len(valid_questions) < len(exam_slots) * 0.8:
            raise Exception(f"Fallo crítico: Solo se generaron {len(valid_questions)}/{len(exam_slots)} preguntas.")

        duration = (datetime.now() - start_time).seconds
        logger.info(f"✅ Examen generado en {duration}s con {len(valid_questions)} preguntas.")
        
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
                logger.warning(f"⚠️ Reintento {attempt+1}/{max_retries} para Slot {slot.topic_id}: {e}")
                if attempt == max_retries:
                    raise e

    async def _process_slot_logic(self, slot: ExamSlot, config: ExamConfig) -> GeneratedQuestion:
        # A. Contexto (RAG)
        chunks = await self.content_selector.fetch_context_for_slot(
            config.course_id, slot.topic_id
        )
        # Preparamos el contexto RAG como string
        rag_context_text = "\n".join([f"- {c.latex_content}" for c in chunks]) if chunks else "No context available."
        
        # B. Estilo (Opcional por ahora)
        # pattern = await self.style_selector.select_best_pattern(...) 
        
        # C. Determinar Tipo Objetivo
        target_q_type = self._determine_question_type(slot, config)

        # D. LLAMADA A LA IA (NUEVA INTEGRACIÓN 4.3)
        # Usamos el método tipado que creamos en AIService
        ai_response_wrapper: ReasoningExamResponse = await self.ai_service.generate_exam_question(
            topic=slot.topic_id,
            difficulty=slot.difficulty.value if isinstance(slot.difficulty, ExamDifficulty) else slot.difficulty,
            question_type=target_q_type.value, # Pasamos el string ('numeric_input')
            rag_context=rag_context_text,
            # kwargs adicionales si el AIService los acepta
            cognitive_type=slot.cognitive_target.value
        )

        # La IA devuelve una lista (aunque pedimos 1). Cogemos la primera.
        if not ai_response_wrapper.questions:
            raise ValueError("La IA devolvió una lista de preguntas vacía.")
            
        ai_question_obj = ai_response_wrapper.questions[0]

        # E. Mapeo (NUEVA LÓGICA DE OBJETOS)
        return self._map_object_to_domain(ai_question_obj, slot, chunks, target_q_type, ai_response_wrapper.chain_of_thought)

    def _determine_question_type(self, slot: ExamSlot, config: ExamConfig) -> QuestionType:
        if config.include_code_questions and slot.cognitive_target in [CognitiveType.COMPUTATIONAL, CognitiveType.DEBUGGING]:
            # Heurística simple: si el tema suena a código
            if any(k in slot.topic_id.lower() for k in ["code", "algo", "python", "java", "loop"]):
                return QuestionType.CODE_EDITOR
        
        if slot.cognitive_target == CognitiveType.CONCEPTUAL:
            return QuestionType.MULTIPLE_CHOICE
            
        return QuestionType.NUMERIC_INPUT

    def _map_object_to_domain(self, ai_q: Any, slot: ExamSlot, chunks: List[EngineeringBlock], target_type: QuestionType, cot: str) -> GeneratedQuestion:
        """
        Transforma el objeto Pydantic de la IA (NumericQuestionAI, etc.) 
        a nuestra entidad de Dominio (GeneratedQuestion).
        """
        validation_rules = None

        # 1. Validación Numérica
        if isinstance(ai_q, NumericQuestionAI):
            validation_rules = NumericalValidation(
                correct_value=ai_q.numeric_rule.correct_value,
                tolerance_percentage=ai_q.numeric_rule.tolerance_percentage,
                allowed_units=ai_q.numeric_rule.allowed_units
            )
            final_type = QuestionType.NUMERIC_INPUT

        # 2. Validación Opción Múltiple
        elif isinstance(ai_q, ChoiceQuestionAI):
            validation_rules = MultipleChoiceValidation(
                options=ai_q.choice_rule.options,
                correct_index=ai_q.choice_rule.correct_index
            )
            final_type = QuestionType.MULTIPLE_CHOICE

        # 3. Validación Código
        elif isinstance(ai_q, CodeQuestionAI):
            tcs = [
                CodeTestCase(input_data=inp, expected_output=out) 
                for inp, out in zip(ai_q.code_rule.test_inputs, ai_q.code_rule.expected_outputs)
            ]
            validation_rules = CodeValidation(test_cases=tcs)
            final_type = QuestionType.CODE_EDITOR
            
        # 4. Fallback (Open Text)
        else:
            final_type = QuestionType.OPEN_TEXT
            # Sin reglas de validación automática estricta

        # Construimos la entidad final
        return GeneratedQuestion(
            statement_latex=ai_q.statement_latex,
            # code_context=ai_q.hint, # Opcional si añades campo de código
            cognitive_type=slot.cognitive_target,
            difficulty=slot.difficulty,
            question_type=final_type,
            source_block_id=chunks[0].id if chunks else "unknown",
            validation_rules=validation_rules,
            step_by_step_solution_latex=ai_q.explanation,
            hint=ai_q.hint
            # Podríamos guardar 'cot' (Chain of Thought) en algún log si quisiéramos
        )