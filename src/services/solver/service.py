import logging
from typing import List, Dict, Any

from src.shared.vectordb.qdrant import QdrantService
from src.services.ai.service import AIService
from src.services.solver.schemas import SolverResponse, SourceReference, SolverRequest
from src.services.solver.prompts import SolverPromptManager

logger = logging.getLogger(__name__)

class SolverService:
    def __init__(self, qdrant_service: QdrantService, ai_service: AIService):
        self.qdrant = qdrant_service
        self.ai = ai_service

    async def solve_doubt(self, request: SolverRequest) -> SolverResponse:
        """
        Flujo principal del Tutor:
        1. Buscar contexto (RAG).
        2. Razonar y Generar respuesta (AI).
        3. Empaquetar con fuentes.
        """
        logger.info(f"🤔 Solver pensando: '{request.question}' para usuario {request.user_id}")

        # 1. RETRIEVAL (RAG)
        # Buscamos chunks relevantes. Si no hay, Qdrant devuelve lista vacía []
        # Importante: Asumimos que tus metadatos tienen 'filename'.
        search_results = await self.qdrant.search(
            query=request.question, 
            limit=3,
            # filters={"user_id": request.user_id} # Descomenta cuando tengas ingesta por usuario
        )
        
        # 2. PREPARAR PROMPTS
        system_prompt = SolverPromptManager.get_system_prompt()
        user_prompt = SolverPromptManager.build_user_context_prompt(
            query=request.question, 
            chunks=search_results, 
            history=request.conversation_history
        )
        
        # 3. GENERATION (AI)
        raw_data = await self.ai.generate_structured_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=SolverResponse
        )
        
        # 4. ENSAMBLAJE
        response = SolverResponse(**raw_data)
        
        # Inyectamos las fuentes reales encontradas (si las hay)
        real_sources = []
        for res in search_results:
            # Solo añadimos fuentes si tienen una relevancia mínima (opcional)
            if res.score > 0.4: 
                real_sources.append(SourceReference(
                    doc_name=res.metadata.get("filename", "Apuntes"),
                    page_number=res.metadata.get("page", None),
                    snippet=res.text[:100] + "...", # Snippet corto para el frontend
                    relevance=res.score
                ))
        
        response.sources = real_sources
        
        return response