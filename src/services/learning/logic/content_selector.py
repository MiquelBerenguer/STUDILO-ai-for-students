from typing import List, Dict
from src.services.learning.domain.entities import ExamConfig, ExamDifficulty
# Mocks/Interfaces
from src.shared.database.repositories import TopicMasteryRepository
from src.shared.vectordb.client import VectorDBClient
from src.services.ai.client import AIService

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

    async def get_available_topics(self, config: ExamConfig) -> List[str]:
        """Determina qué temas entran en el examen (Input para el Blueprint)."""
        if config.topic_ids:
            return config.topic_ids
            
        # Lógica ADAPTIVE: Buscar debilidades
        if config.difficulty == ExamDifficulty.ADAPTIVE:
            weak_topics = await self.mastery_repo.get_weakest_topics(
                student_id=config.student_id,
                course_id=config.course_id
            )
            if weak_topics:
                return [t.topic_id for t in weak_topics]
        
        # Fallback: Todos los temas del curso
        return await self.mastery_repo.get_all_topics(config.course_id)

    async def fetch_context_for_slot(self, course_id: str, topic_id: str) -> List[str]:
        """
        Recupera chunks específicos para UNA pregunta (Slot) del Blueprint.
        """
        # Búsqueda semántica simple por ahora (podemos activar query expansion luego)
        chunks = await self.vector_db.search(
            query=f"conceptos clave examen {topic_id}", 
            filters={
                "course_id": course_id,
                "topic_id": topic_id
            },
            limit=3
        )
        return [chunk.text for chunk in chunks]