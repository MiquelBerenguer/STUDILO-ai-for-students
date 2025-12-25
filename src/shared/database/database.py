from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings # 1. Importamos la fuente única de verdad

# 2. Construcción de URL usando settings
# Nota: Usamos el driver psycopg2 por defecto
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# 3. Creación del Motor con Tuning de Pool
# pool_pre_ping=True: Verifica la conexión antes de usarla (evita errores de "connection lost")
# pool_size: Conexiones mantenidas abiertas permanentemente.
# max_overflow: Conexiones extra permitidas durante picos de tráfico.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,          # Resiliencia: Detecta desconexiones
    pool_size=settings.DB_POOL_SIZE,        # Escalabilidad: Mantiene conexiones listas
    max_overflow=settings.DB_MAX_OVERFLOW,  # Elasticidad: Maneja picos 
    pool_recycle=3600            # Mantenimiento: Recicla conexiones cada hora
)

# Fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa para los modelos
Base = declarative_base()

# Dependencia (Dependency Injection)
def get_db():
    db = SessionLocal()
    try:
        # yield permite usar la sesión y cerrarla automáticamente después del request
        yield db
    finally:
        db.close()