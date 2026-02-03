import logging
from typing import Optional, Dict, Any, Union
import openai
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

# --- CONFIGURACIÓN ---
from src.services.ai.config import get_ai_settings

# --- ENTIDADES (Inputs) ---
from src.services.learning.domain.entities import (
    ExamDifficulty,
    QuestionType,
    CognitiveType,
    Language
)

# --- SCHEMAS (Outputs Estructurados) ---
# 🔥 CORRECCIÓN AQUÍ: Añadimos AIReasoningEvaluation a la importación
from src.services.learning.schemas import (
    ReasoningQuestionResponse, 
    AIReasoningEvaluation 
)

# --- PROMPTS ---
from src.services.ai.prompts import PromptManager

logger = logging.getLogger(__name__)
settings = get_ai_settings()

class AIService:
    def __init__(self, client: Optional[AsyncOpenAI] = None):
        """
        Inicializa el servicio de IA.
        """
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"

    def _safe_value(self, item: Any) -> str:
        """Helper para extraer valor de Enum o String de forma segura."""
        if hasattr(item, 'value'):
            return str(item.value)
        return str(item)

    # -------------------------------------------------------------------------
    # 1. GENERACIÓN DE EXÁMENES (Lógica antigua, mantenida)
    # -------------------------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.InternalServerError,
            ValueError
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def generate_exam_question(
        self,
        topic: str,
        difficulty: Union[ExamDifficulty, str],
        question_type: Union[QuestionType, str],
        cognitive_type: Union[CognitiveType, str],
        rag_context: str,
        language: Language = Language.ES
    ) -> Dict[str, Any]:
        """
        Genera una pregunta de examen validada y estructurada.
        """
        
        # Preparación segura de valores
        diff_val = self._safe_value(difficulty)
        q_type_val = self._safe_value(question_type)
        cog_val = self._safe_value(cognitive_type)

        system_prompt = PromptManager.get_examiner_system_prompt(language) if hasattr(PromptManager, 'get_examiner_system_prompt') else "Eres un profesor experto."
        
        user_task_prompt = PromptManager.get_engineering_prompt(
            topic=topic,
            difficulty=diff_val,
            cognitive_type=cog_val,
            points=10.0,
            rag_context=rag_context,
            question_type=q_type_val
        )

        logger.info(f"🧠 AI Generando: {q_type_val} sobre '{topic}' [Dificultad: {diff_val}]")

        try:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_task_prompt}
                ],
                response_format=ReasoningQuestionResponse, 
                temperature=0.2, 
            )

            if completion.usage:
                logger.info(f"💰 Consumo AI: {completion.usage.total_tokens} tokens")

            response_wrapper = completion.choices[0].message.parsed
            
            if not response_wrapper:
                raise ValueError("OpenAI devolvió una respuesta vacía.")

            logger.debug(f"💭 Razonamiento AI: {response_wrapper.chain_of_thought}")

            return response_wrapper.model_dump() 

        except Exception as e:
            logger.error(f"❌ Error en AIService (Examen): {str(e)}")
            raise e

    # -------------------------------------------------------------------------
    # 2. MÉTODO GENÉRICO ESTRUCTURADO (Nuevo: Usado por el Solver)
    # -------------------------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            openai.APIConnectionError, 
            openai.RateLimitError, 
            openai.InternalServerError
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def generate_structured_response(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_model: Any, # Clase Pydantic flexible
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Método genérico para generar respuestas estructuradas (JSON) usando Pydantic.
        Se usa para Solver, Feedback y futuros agentes.
        """
        try:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=response_model,
                temperature=temperature,
            )
            
            parsed_obj = completion.choices[0].message.parsed
            
            if not parsed_obj:
                raise ValueError("OpenAI devolvió una respuesta vacía o inválida.")
                
            return parsed_obj.model_dump()

        except Exception as e:
            logger.error(f"❌ Error generando respuesta estructurada: {e}")
            raise e

    # -------------------------------------------------------------------------
    # 3. LEGACY / COMPATIBILIDAD
    # -------------------------------------------------------------------------
    async def generate_json(self, prompt: str, model: str = None, temperature: float = 0.2) -> Dict[str, Any]:
        """
        Método 'passthrough' simple.
        """
        try:
            completion = await self.client.beta.chat.completions.parse(
                model=model or self.model,
                messages=[
                    {"role": "system", "content": "Eres un arquitecto de exámenes experto."},
                    {"role": "user", "content": prompt}
                ],
                response_format=ReasoningQuestionResponse,
                temperature=temperature,
            )
            return completion.choices[0].message.parsed.model_dump()
        except Exception as e:
            logger.error(f"❌ Error en generate_json: {e}")
            raise e

    # -------------------------------------------------------------------------
    # 4. CORRECCIÓN INTELIGENTE (The Judge)
    # -------------------------------------------------------------------------
    async def evaluate_reasoning(self, question_text: str, correct_value: str, student_value: str, student_procedure: str) -> dict:
        """Evalúa si un alumno merece puntos parciales analizando su texto."""
        # 1. Construir Prompts
        sys_prompt = PromptManager.get_grader_system_prompt()
        user_prompt = PromptManager.build_grader_user_prompt(question_text, correct_value, student_value, student_procedure)

        logger.info(f"⚖️ AI Judging: Evaluando procedimiento para respuesta: {student_value}")

        # 2. Llamada a LLM usando tu método genérico existente
        return await self.generate_structured_response(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            response_model=AIReasoningEvaluation, # AHORA SÍ ESTÁ DEFINIDO ✅
            temperature=0.2 
        )