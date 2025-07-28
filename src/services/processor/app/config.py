from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Configuración del servicio
    service_name: str = "processor-service"
    service_port: int = 8002
    debug: bool = False
    
    # Base de datos
    database_url: str = "postgresql://REDACTED:REDACTED@postgres:5432/tutor_db"
    
    # Redis
    redis_url: str = "redis://redis:6379/0"
    
    # MinIO (S3-compatible)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"
    minio_secure: bool = False
    
    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    
    # Configuración de procesamiento
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    supported_formats: list = ["pdf", "png", "jpg", "jpeg", "txt"]
    ocr_languages: list = ["spa", "eng"]
    
    # Configuración de workers
    max_workers: int = 4
    processing_timeout: int = 300  # 5 minutos
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()
