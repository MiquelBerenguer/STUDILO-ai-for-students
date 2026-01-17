from typing import List, Any, Union
import logging

# CORRECCIÓN: Añadimos PedagogicalPattern y EngineeringBlock a los imports
from src.services.learning.domain.entities import (
    ExamConfig, 
    ExamDifficulty, 
    PedagogicalPattern, 
    EngineeringBlock
)

# Mocks/Interfaces
from src.shared.database.repositories import TopicMasteryRepository
from src.shared.vectordb.client import VectorDBClient
from src.services.ai.service import AIService

logger = logging.getLogger(__name__)

class ContentSelector:
    def __init__(
        self, 
        mastery_repo: TopicMasteryRepository,
        vector_db: VectorDBClient,
        ai_service: AIService
    ):
        self.mastery_repo = mastery_repo
        self.vector_db = vector_db
        self.ai_service = ai_service

    def _safe_str(self, val: Any) -> str:
        """
        🛡️ Helper de Robustez: 
        Evita el error 'str object has no attribute value' si nos llega un string,
        y extrae el valor correctamente si nos llega un Enum.
        """
        if isinstance(val, str):
            return val
        if hasattr(val, "value"): # Es un Enum
            return str(val.value)
        return str(val)

    async def get_available_topics(self, config: ExamConfig) -> List[str]:
        """Determina qué temas entran en el examen (Input para el Blueprint)."""
        
        # CORRECCIÓN 1: Usamos el nombre real del campo en ExamConfig
        if config.topics_include:
            return config.topics_include
            
        # CORRECCIÓN 2: ADAPTIVE es un Pattern, no una Difficulty
        # Usamos logica defensiva aqui tambien
        if config.pattern == PedagogicalPattern.ADAPTIVE:
            try:
                weak_topics = await self.mastery_repo.get_weakest_topics(
                    student_id=config.student_id,
                    course_id=config.course_id
                )
                
                # Normalización defensiva de la respuesta del repo
                clean_topics = []
                if weak_topics:
                    for t in weak_topics:
                        if hasattr(t, 'topic_id'):
                            clean_topics.append(t.topic_id)
                        elif isinstance(t, dict):
                            clean_topics.append(t.get('topic_id') or t.get('topic'))
                        else:
                            clean_topics.append(str(t))
                return clean_topics
            except Exception as e:
                logger.warning(f"⚠️ Fallo en modo ADAPTIVE, fallback a todos los temas: {e}")
        
        # Fallback: Todos los temas del curso
        return await self.mastery_repo.get_all_topics(config.course_id)

    async def fetch_context_for_slot(self, course_id: str, topic_id: str) -> List[EngineeringBlock]:
        """
        Recupera chunks específicos para UNA pregunta (Slot) del Blueprint.
        """
        # --- BLINDAJE PASO 1: Sanitización de Inputs ---
        c_id = self._safe_str(course_id)
        t_id = self._safe_str(topic_id)

        try:
            # Búsqueda semántica
            # Al usar c_id y t_id (strings puros), garantizamos que no explote
            raw_chunks = await self.vector_db.search(
                query=f"conceptos clave examen {t_id}", 
                filters={
                    "course_id": c_id,
                    "topic_id": t_id
                },
                limit=3
            )
            
            # --- BLINDAJE PASO 2: Hidratación de Respuesta ---
            # Aseguramos devolver objetos EngineeringBlock, nunca dicts ni strings
            hydrated_chunks = []
            
            if not raw_chunks:
                return []

            for chunk in raw_chunks:
                if isinstance(chunk, EngineeringBlock):
                    hydrated_chunks.append(chunk)
                elif isinstance(chunk, dict):
                    # Si VectorDB devuelve un dict, lo convertimos
                    try:
                        hydrated_chunks.append(EngineeringBlock(**chunk))
                    except Exception as e:
                        logger.warning(f"Error hidratando chunk desde dict: {e}")
                else:
                    # Caso borde: string o desconocido
                    hydrated_chunks.append(EngineeringBlock(
                        id="unknown",
                        course_id=c_id,
                        source_type="theory", # valor por defecto seguro
                        clean_text=str(chunk),
                        latex_content=str(chunk)
                    ))
            
            return hydrated_chunks

        except Exception as e:
            logger.error(f"Error recuperando contexto para {t_id}: {e}")
            # Retornar lista vacía es mejor que romper el examen entero
            return []