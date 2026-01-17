import logging
import asyncio
import json
from datetime import datetime
from typing import List, Any, Union

# --- IMPORTS DE DOMINIO ---
from src.services.learning.domain.entities import (
    ExamConfig, Exam, GeneratedQuestion, 
    QuestionType, CognitiveType,
    NumericalValidation, CodeValidation, MultipleChoiceValidation,
    CodeTestCase, EngineeringBlock, ExamDifficulty
)

# --- IMPORTS DE INFRAESTRUCTURA ---
from src.services.ai.service import AIService
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

    def _to_str(self, value: Any) -> str:
        """Helper Robusto: Extrae el valor string de un Enum o devuelve el string tal cual."""
        if isinstance(value, str):
            return value
        if hasattr(value, 'value'):
            return str(value.value)
        return str(value)

    async def generate_exam(self, config: ExamConfig) -> Exam:
        start_time = datetime.now()
        logger.info(f"🏗️  INICIANDO FACTORÍA DE EXAMEN: {config.course_id}")

        topics = await self.content_selector.get_available_topics(config)
        exam_slots = self.blueprint_builder.create_blueprint(config, topics)
        
        logger.info(f"🚀 Lanzando generación de {len(exam_slots)} preguntas...")
        
        tasks = [
            self._generate_single_question_safely(slot, config) 
            for slot in exam_slots
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_questions = []
        for i, result in enumerate(results):
            if isinstance(result, GeneratedQuestion):
                valid_questions.append(result)
            else:
                logger.error(f"❌ Fallo Slot {i}: {result}")
        
        if len(valid_questions) == 0:
            raise Exception("Fallo crítico: No se generó ninguna pregunta válida.")

        duration = (datetime.now() - start_time).seconds
        logger.info(f"✅ Generado en {duration}s: {len(valid_questions)}/{len(exam_slots)} preguntas.")
        
        return Exam(
            config=config,
            questions=valid_questions,
            created_at=datetime.utcnow(),
            status="ready"
        )

    async def _generate_single_question_safely(self, slot: ExamSlot, config: ExamConfig) -> GeneratedQuestion:
        try:
            return await self._process_slot_logic(slot, config)
        except Exception as e:
            logger.error(f"🔥 Error en Slot {slot.topic_id}: {e}", exc_info=True)
            raise e

    async def _process_slot_logic(self, slot: ExamSlot, config: ExamConfig) -> GeneratedQuestion:
        # A. Contexto
        chunks = await self.content_selector.fetch_context_for_slot(config.course_id, slot.topic_id)
        rag_text = "\n".join([f"- {c.latex_content or c.clean_text}" for c in chunks]) if chunks else "General knowledge."
        
        # B. Tipo Objetivo y Metadatos
        target_q_type = self._determine_question_type(slot, config)
        str_difficulty = self._to_str(slot.difficulty)
        str_cognitive = self._to_str(slot.cognitive_target)

        # C. Llamada a IA
        ai_response = await self.ai_service.generate_exam_question(
            topic=slot.topic_id,
            difficulty=str_difficulty,
            question_type=self._to_str(target_q_type),
            rag_context=rag_text,
            cognitive_type=str_cognitive
        )

        # --- FASE DE SANITIZACIÓN (Ingeniería de Datos) ---
        
        # 1. Asegurar que es un dict
        if isinstance(ai_response, str):
            try:
                ai_response = json.loads(ai_response)
            except json.JSONDecodeError:
                # Intento de limpieza si trae markdown
                cleaned = ai_response.replace("```json", "").replace("```", "").strip()
                try:
                    ai_response = json.loads(cleaned)
                except:
                    # Último recurso: tratar todo el string como enunciado
                    ai_response = {"statement_latex": ai_response}

        # 2. Desempaquetado seguro
        raw_data = ai_response
        if "questions" in ai_response and isinstance(ai_response["questions"], list):
            if ai_response["questions"]:
                raw_data = ai_response["questions"][0]

        # 3. CONSTRUCCIÓN DE PAYLOAD LIMPIO (Clean Build Pattern)
        # No confiamos en raw_data directamente. Construimos clean_data campo a campo.
        clean_data = {}

        # -- Extracción del Enunciado (El punto de fallo anterior) --
        # Buscamos en varias claves posibles
        raw_statement = (
            raw_data.get("statement_latex") or 
            raw_data.get("statement") or 
            raw_data.get("question") or 
            raw_data.get("content")
        )

        # SI EL ENUNCIADO ES UN DICCIONARIO (El error actual), sacamos el texto de dentro
        if isinstance(raw_statement, dict):
            clean_data["statement_latex"] = (
                raw_statement.get("text") or 
                raw_statement.get("statement") or 
                raw_statement.get("content") or 
                str(raw_statement) # Fallback a stringify
            )
        elif raw_statement:
            clean_data["statement_latex"] = str(raw_statement)
        else:
            clean_data["statement_latex"] = "Pregunta generada (texto no disponible)."

        # -- Inyección de Metadatos (Single Source of Truth) --
        clean_data["difficulty"] = str_difficulty
        clean_data["cognitive_type"] = str_cognitive

        # -- Extracción de Explicación --
        raw_explanation = raw_data.get("explanation") or raw_data.get("chain_of_thought")
        if isinstance(raw_explanation, dict):
            clean_data["explanation"] = str(raw_explanation) # Aplanar si es dict
        else:
            clean_data["explanation"] = str(raw_explanation or "Solución paso a paso.")

        # -- Reconstrucción de Reglas Específicas --
        if target_q_type == QuestionType.NUMERIC_INPUT:
            # A veces la IA devuelve 'numeric_solution' suelto en la raíz
            source_rule = raw_data.get("numeric_rule", raw_data)
            clean_data["numeric_rule"] = {
                "correct_value": source_rule.get("correct_value") or source_rule.get("numeric_solution", 0),
                "tolerance_percentage": source_rule.get("tolerance_percentage") or source_rule.get("tolerance_percent", 5),
                "allowed_units": source_rule.get("allowed_units") or source_rule.get("units", [])
            }

        elif target_q_type == QuestionType.MULTIPLE_CHOICE:
            source_rule = raw_data.get("choice_rule", raw_data)
            clean_data["choice_rule"] = {
                "options": source_rule.get("options", ["Opción A", "Opción B"]),
                "correct_index": source_rule.get("correct_index") or source_rule.get("correct_option_index", 0)
            }
            
        elif target_q_type == QuestionType.CODE_EDITOR:
             source_rule = raw_data.get("code_rule", raw_data)
             clean_data["code_rule"] = {
                 "test_inputs": source_rule.get("test_inputs", ["input1"]),
                 "expected_outputs": source_rule.get("expected_outputs", ["output1"])
             }

        # 4. Hidratación Pydantic (Ahora con datos limpios)
        ai_q_object = None
        try:
            if target_q_type == QuestionType.NUMERIC_INPUT:
                ai_q_object = NumericQuestionAI(**clean_data)
            elif target_q_type == QuestionType.MULTIPLE_CHOICE:
                ai_q_object = ChoiceQuestionAI(**clean_data)
            elif target_q_type == QuestionType.CODE_EDITOR:
                ai_q_object = CodeQuestionAI(**clean_data)
            else:
                ai_q_object = OpenQuestionAI(**clean_data)
        except Exception as e:
            logger.error(f"Error validando esquema {target_q_type}: {e} | Data: {clean_data}")
            # Fallback final a OpenQuestion para no romper el flujo
            try:
                # Quitamos reglas complejas para que pase como Open
                clean_data.pop("numeric_rule", None)
                clean_data.pop("choice_rule", None)
                ai_q_object = OpenQuestionAI(**clean_data)
            except:
                raise ValueError(f"Error estructural irrecuperable: {e}")

        # 5. Mapeo a Entidad de Dominio
        return self._map_object_to_domain(ai_q_object, slot, chunks, target_q_type)

    def _determine_question_type(self, slot: ExamSlot, config: ExamConfig) -> QuestionType:
        if config.include_code_questions:
            topic_lower = slot.topic_id.lower()
            if any(k in topic_lower for k in ["code", "algo", "python", "loop"]):
                 return QuestionType.CODE_EDITOR
        
        cog_val = self._to_str(slot.cognitive_target)
        if cog_val == self._to_str(CognitiveType.CONCEPTUAL):
            return QuestionType.MULTIPLE_CHOICE
            
        return QuestionType.NUMERIC_INPUT

    def _map_object_to_domain(self, ai_q: Any, slot: ExamSlot, chunks: List[EngineeringBlock], target_type: QuestionType) -> GeneratedQuestion:
        
        validation_rules = None
        final_type = target_type

        # Mapeo de reglas de validación
        if isinstance(ai_q, NumericQuestionAI):
            validation_rules = NumericalValidation(
                correct_value=ai_q.numeric_rule.correct_value,
                tolerance_percentage=ai_q.numeric_rule.tolerance_percentage,
                allowed_units=ai_q.numeric_rule.allowed_units
            )
            final_type = QuestionType.NUMERIC_INPUT
        elif isinstance(ai_q, ChoiceQuestionAI):
            validation_rules = MultipleChoiceValidation(
                options=ai_q.choice_rule.options,
                correct_index=ai_q.choice_rule.correct_index
            )
            final_type = QuestionType.MULTIPLE_CHOICE
        elif isinstance(ai_q, CodeQuestionAI):
             tcs = [CodeTestCase(input_data=i, expected_output=o) for i, o in zip(ai_q.code_rule.test_inputs, ai_q.code_rule.expected_outputs)]
             validation_rules = CodeValidation(test_cases=tcs)
             final_type = QuestionType.CODE_EDITOR
        else:
            final_type = QuestionType.OPEN_TEXT

        return GeneratedQuestion(
            statement_latex=ai_q.statement_latex,
            cognitive_type=slot.cognitive_target if isinstance(slot.cognitive_target, CognitiveType) else CognitiveType.COMPUTATIONAL,
            difficulty=slot.difficulty if isinstance(slot.difficulty, ExamDifficulty) else ExamDifficulty.APPLIED,
            question_type=final_type,
            source_block_id=chunks[0].id if chunks else "unknown",
            validation_rules=validation_rules,
            step_by_step_solution_latex=ai_q.explanation,
            hint=ai_q.hint
        )