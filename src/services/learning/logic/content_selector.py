from typing import List, Any
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
        
        # CORRECCIÓN 1: Usamos el nombre real del campo en ExamConfig
        if config.topics_include:
            return config.topics_include
            
        # CORRECCIÓN 2: ADAPTIVE es un Pattern, no una Difficulty
        if config.pattern == PedagogicalPattern.ADAPTIVE:
            weak_topics = await self.mastery_repo.get_weakest_topics(
                student_id=config.student_id,
                course_id=config.course_id
            )
            # Asumimos que el repo devuelve objetos con atributo topic_id
            if weak_topics:
                return [t.topic_id if hasattr(t, 'topic_id') else t['topic'] for t in weak_topics]
        
        # Fallback: Todos los temas del curso
        return await self.mastery_repo.get_all_topics(config.course_id)

    async def fetch_context_for_slot(self, course_id: str, topic_id: str) -> List[EngineeringBlock]:
        """
        Recupera chunks específicos para UNA pregunta (Slot) del Blueprint.
        """
        # Búsqueda semántica
        chunks = await self.vector_db.search(
            query=f"conceptos clave examen {topic_id}", 
            filters={
                "course_id": course_id,
                "topic_id": topic_id
            },
            limit=3
        )
        
        # CORRECCIÓN 3: Devolvemos los objetos completos (EngineeringBlock), 
        # no solo strings. El ExamGenerator necesita acceder a .latex_content
        return chunks