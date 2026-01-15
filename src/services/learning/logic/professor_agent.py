from typing import List, Dict, Any, Optional
from src.services.learning.api.schemas import ChatRequest, ChatResponse

# CONEXIÓN AL CEREBRO CENTRAL (La clave de la arquitectura)
from src.services.ai.prompts import PromptManager
from src.services.learning.domain.entities import Language

class ProfessorAgent:
    def __init__(self):
        # ✅ LIMPIO: Ya no escribimos el texto aquí. Lo pedimos al Manager.
        # Por defecto usamos Español (ES), pero podríamos pasarlo en el __init__
        self.system_prompt = PromptManager.get_tutor_system_prompt(Language.ES)

    async def ask(self, request: ChatRequest) -> ChatResponse:
        """
        Procesa el mensaje aplicando la metodología del Mentor.
        """
        
        # 1. Recuperar contexto (Simulación RAG)
        # Aquí buscaríamos en la Vector DB usando request.context_files
        context_chunks = "Contenido simulado extraído de los PDFs..." 

        # 2. Construir el Prompt del Usuario (Usando el Manager)
        # ✅ LIMPIO: Delegamos la estructura del mensaje del usuario también
        user_prompt = PromptManager.build_chat_user_prompt(
            query=request.message, # Asumo que request tiene un campo 'message' o 'query'
            context_chunks=context_chunks
        )

        # 3. Llamada al LLM (Simulada por ahora)
        # En el futuro aquí llamarás a: await ai_service.chat(system=self.system_prompt, user=user_prompt)
        
        # MOCK RESPONSE (Simulando paso 2: Active Recall)
        response_text = (
            "He analizado el PDF. Antes de definir la Entropía, "
            "basándote en la diapositiva 14, ¿cómo explicarías el 'Desorden'?"
        )

        return ChatResponse(
            response=response_text,
            methodology_step="Active Recall / Scaffolding",
            sources=["Diapositiva 14", "Apuntes Tema 3"]
        )

# Instancia Singleton
professor_agent = ProfessorAgent()