from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
import structlog
from ..config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Convertir URL de PostgreSQL a formato asyncpg
DATABASE_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

# Crear engine asíncrono
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Cambiar a True para debug
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,  # Verificar conexiones antes de usar
    pool_recycle=3600,   # Reciclar conexiones cada hora
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base para modelos
Base = declarative_base()

# Dependency para obtener sesión de DB
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Función para verificar conexión
async def check_database_connection():
    try:
        async with engine.begin() as conn:
            # Usar text() para consultas SQL raw
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False


# Crear tablas
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)