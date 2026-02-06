import os
from pydantic_settings import BaseSettings

class SharedSettings(BaseSettings):
    """
    Configuración Limpia y Moderna.
    Solo URLs completas y variables esenciales.
    """
    PROJECT_NAME: str = "TutorIA Platform"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = os.getenv("JWT_SECRET", "REDACTED")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Infraestructura Limpia
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL")
    
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_USER: str = "minioadmin"
    MINIO_PASSWORD: str = "minioadmin"
    
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # Topología (Opcionales con defaults sensatos)
    EXAM_EXCHANGE_NAME: str = "tutor.exams"
    EXAM_QUEUE_NAME: str = "exams_queue" # Coincide con el worker
    EXAM_DLQ_NAME: str = "exam.generate.dlq"
    MESSAGE_TTL_MS: int = 300000 

    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = SharedSettings()