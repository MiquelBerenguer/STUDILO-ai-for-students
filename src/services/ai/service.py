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
from src.services.learning.schemas import ReasoningQuestionResponse

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
        difficulty: Union[ExamDifficulty, str], # Permitimos ambos
        question_type: Union[QuestionType, str],
        cognitive_type: Union[CognitiveType, str],
        rag_context: str,
        language: Language = Language.ES
    ) -> Dict[str, Any]:
        """
        Genera una pregunta de examen validada y estructurada.
        Retorna un dict con keys: 'chain_of_thought' y 'content'.
        """
        
        # 1. PREPARACIÓN (Usando helper safe_value)
        # Esto evita el error 'str object has no attribute value'
        diff_val = self._safe_value(difficulty)
        q_type_val = self._safe_value(question_type)
        cog_val = self._safe_value(cognitive_type)

        system_prompt = PromptManager.get_examiner_system_prompt(language) if hasattr(PromptManager, 'get_examiner_system_prompt') else "Eres un profesor experto."
        
        # Pasamos valores seguros al PromptManager
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
            # 2. EJECUCIÓN (Native Structured Outputs)
            completion = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_task_prompt}
                ],
                # Forzamos el esquema Pydantic nuevo (ReasoningQuestionResponse)
                response_format=ReasoningQuestionResponse, 
                temperature=0.2, 
            )

            # 3. OBSERVABILIDAD
            if completion.usage:
                logger.info(
                    f"💰 Consumo AI: {completion.usage.total_tokens} tokens "
                    f"(Prompt: {completion.usage.prompt_tokens}, Compl: {completion.usage.completion_tokens})"
                )

            # 4. EXTRACCIÓN Y LIMPIEZA
            response_wrapper = completion.choices[0].message.parsed
            
            if not response_wrapper:
                raise ValueError("OpenAI devolvió una respuesta vacía o imposible de parsear.")

            logger.debug(f"💭 Razonamiento AI: {response_wrapper.chain_of_thought}")

            # Convertimos a dict puro usando model_dump() (Pydantic v2)
            full_dump = response_wrapper.model_dump()
            
            # Devolvemos TODO el objeto
            return full_dump 

        except Exception as e:
            logger.error(f"❌ Error en AIService: {str(e)}")
            raise e

    # --- MÉTODO COMPATIBILIDAD ---
    async def generate_json(self, prompt: str, model: str = None, temperature: float = 0.2) -> Dict[str, Any]:
        """
        Método 'passthrough' por si ExamGenerator quiere control total del prompt.
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