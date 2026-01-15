import logging
from typing import Optional, Dict, Any
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
# Importamos desde la ruta correcta que creamos (sin 'api')
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
        # CORRECCIÓN DE INGENIERÍA: Pydantic v2 guarda los settings en minúscula
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

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
        difficulty: ExamDifficulty,
        question_type: QuestionType,
        cognitive_type: CognitiveType,
        rag_context: str,
        language: Language = Language.ES
    ) -> Dict[str, Any]:
        """
        Genera una pregunta de examen validada y estructurada.
        """
        
        # 1. PREPARACIÓN (Prompt Engineering Interno)
        # Nota: Si tu ExamGenerator ya construye el prompt fuera, adaptaremos este método luego.
        # Por ahora, mantenemos la lógica robusta original.
        
        system_prompt = PromptManager.get_examiner_system_prompt(language) if hasattr(PromptManager, 'get_examiner_system_prompt') else "Eres un profesor experto."
        
        user_task_prompt = PromptManager.get_engineering_prompt(
            topic=topic,
            difficulty=difficulty,
            cognitive_type=cognitive_type,
            points=10.0,
            rag_context=rag_context,
            question_type=question_type
        )

        logger.info(f"🧠 AI Generando: {question_type.value} sobre '{topic}' [Dificultad: {difficulty.value}]")

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
            # Esto devuelve {'chain_of_thought': '...', 'content': {'statement_latex': '...', ...}}
            # IMPORTANTE: Tu ExamGenerator espera recibir solo el contenido interior o el objeto completo?
            # Basado en tu código anterior, devolvemos el objeto 'content' limpio:
            
            full_dump = response_wrapper.model_dump()
            
            # Devolvemos el contenido de la pregunta (NumericContent, ChoiceContent, etc.)
            return full_dump['content']

        except Exception as e:
            logger.error(f"❌ Error en AIService: {str(e)}")
            raise e

    # --- MÉTODO COMPATIBILIDAD (SI EXAM_GENERATOR LO PIDE) ---
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
            return completion.choices[0].message.parsed.content.model_dump()
        except Exception as e:
            logger.error(f"❌ Error en generate_json: {e}")
            raise e