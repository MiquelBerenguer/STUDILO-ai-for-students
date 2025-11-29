from fastapi import Depends
import asyncpg
from src.shared.infrastructure.db import DatabasePool
from src.shared.database.repositories import PostgresPatternRepository, PostgresTopicMasteryRepository

# Servicios de Dominio
from src.services.learning.logic.style_selector import StyleSelector
# from src.services.learning.logic.exam_generator import ExamGenerator # Descomentar cuando tengamos el blueprint builder listo

# 1. Inyección del Pool de DB
async def get_db_pool() -> asyncpg.Pool:
    return DatabasePool.get_pool()

# 2. Inyección de Repositorios (Repository Pattern)
async def get_pattern_repo(pool: asyncpg.Pool = Depends(get_db_pool)) -> PostgresPatternRepository:
    return PostgresPatternRepository(pool)

async def get_topic_repo(pool: asyncpg.Pool = Depends(get_db_pool)) -> PostgresTopicMasteryRepository:
    return PostgresTopicMasteryRepository(pool)

# 3. Inyección de Servicios (Application Layer)
async def get_style_selector(
    pattern_repo: PostgresPatternRepository = Depends(get_pattern_repo)
) -> StyleSelector:
    """
    FastAPI construirá automáticamente:
    Pool -> Repository -> StyleSelector
    """
    return StyleSelector(pattern_repo)