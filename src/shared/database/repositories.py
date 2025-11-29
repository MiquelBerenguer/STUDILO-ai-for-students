from abc import ABC, abstractmethod
from typing import List, Optional, Any
import asyncpg
from src.services.learning.domain.entities import (
    CognitiveType, ExamDifficulty, PatternScope, PedagogicalPattern
)

# --- 1. INTERFACES (Contratos) ---
# Mantenemos esto porque es buena arquitectura (Dependency Inversion)

class TopicMasteryRepository(ABC):
    @abstractmethod
    async def get_weakest_topics(self, student_id: str, course_id: str, limit: int = 5) -> List[dict]:
        pass

    @abstractmethod
    async def get_all_topics(self, course_id: str) -> List[str]:
        pass

class PatternRepository(ABC):
    @abstractmethod
    async def find_patterns(
        self, 
        scope: PatternScope, 
        cognitive_type: Optional[CognitiveType] = None, 
        difficulty: Optional[ExamDifficulty] = None, 
        target_id: Optional[str] = None
    ) -> List[PedagogicalPattern]:
        pass


# --- 2. IMPLEMENTACIÓN REAL (PostgreSQL) ---
# Aquí es donde ocurre la magia y conectamos con tu nueva DB limpia.

class PostgresPatternRepository(PatternRepository):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def find_patterns(
        self, 
        scope: PatternScope, 
        cognitive_type: Optional[CognitiveType] = None, 
        difficulty: Optional[ExamDifficulty] = None, 
        target_id: Optional[str] = None
    ) -> List[PedagogicalPattern]:
        
        # Construcción dinámica de la query
        query = """
            SELECT id, scope, target_id, cognitive_type, difficulty, reasoning_recipe, original_question
            FROM pedagogical_patterns
            WHERE scope = $1
        """
        params = [scope.value] # $1
        param_counter = 2

        if cognitive_type:
            query += f" AND cognitive_type = ${param_counter}"
            params.append(cognitive_type.value)
            param_counter += 1
        
        if difficulty:
            query += f" AND difficulty = ${param_counter}"
            params.append(difficulty.value)
            param_counter += 1
            
        if target_id:
            query += f" AND target_id = ${param_counter}"
            params.append(str(target_id))
            param_counter += 1

        # Ejecutamos contra la DB
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
        # Mapeamos de SQL (filas) a Objetos de Dominio (Entidades)
        patterns = []
        for row in rows:
            patterns.append(PedagogicalPattern(
                id=str(row['id']),
                scope=PatternScope(row['scope']),
                target_id=row['target_id'],
                cognitive_type=CognitiveType(row['cognitive_type']),
                difficulty=ExamDifficulty(row['difficulty']),
                reasoning_recipe=row['reasoning_recipe'],
                original_question=row['original_question']
            ))
            
        return patterns


class PostgresTopicMasteryRepository(TopicMasteryRepository):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_all_topics(self, course_id: str) -> List[str]:
        """Obtiene lista simple de nombres de temas desde la tabla 'topics'."""
        query = "SELECT name FROM topics WHERE course_id = $1"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, course_id)
            
        return [row['name'] for row in rows]

    async def get_weakest_topics(self, student_id: str, course_id: str, limit: int = 5) -> List[dict]:
        """
        JOIN CRÍTICO: Une 'topic_mastery' con 'topics' para saber el nombre del tema.
        Ordena por failures DESC (lo que más fallas) y mastery ASC (lo que menos sabes).
        """
        query = """
            SELECT t.name, tm.mastery_level, tm.consecutive_failures
            FROM topic_mastery tm
            JOIN topics t ON tm.topic_id = t.id
            WHERE tm.student_id = $1 AND tm.course_id = $2
            ORDER BY tm.consecutive_failures DESC, tm.mastery_level ASC
            LIMIT $3
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, student_id, course_id, limit)
            
        # Retornamos dicts simples por ahora para que el Planner los use
        return [
            {"topic": row['name'], "mastery": row['mastery_level'], "failures": row['consecutive_failures']}
            for row in rows
        ]