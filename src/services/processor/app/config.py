"""
Configuration module for the Processor service
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Application settings
    app_name: str = "Tutor IA Processor Service"
    service_name: str = "processor"
    service_port: int = 8002
    debug: bool = False
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8002
    
    # Database settings - Usar nombres correctos de docker-compose
    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres-master")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "tutor_db")
    postgres_user: str = os.getenv("POSTGRES_USER", "REDACTED")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "REDACTED")
    
    # MinIO settings - Usar variables de entorno del docker-compose
    minio_host: str = os.getenv("MINIO_ENDPOINT", "minio").split(":")[0]
    minio_port: int = 9000
    minio_access_key: str = os.getenv("MINIO_USER", "REDACTED")
    minio_secret_key: str = os.getenv("MINIO_PASSWORD", "REDACTED")
    minio_bucket_name: str = "documents"
    minio_secure: bool = False
    
    # Redis settings - Usar nombre correcto y password
    redis_host: str = os.getenv("REDIS_HOST", "redis-primary")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = 0
    REDACTED: Optional[str] = os.getenv("REDIS_PASSWORD", "REDACTED")
    
    # RabbitMQ settings - Usar vhost correcto
    rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user: str = os.getenv("RABBITMQ_USER", "admin")
    rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "REDACTED")
    rabbitmq_vhost: str = "tutor_ia"  # Cambiado de "/" a "tutor_ia" como está en docker-compose
    
    # Processing settings
    max_file_size_mb: int = 50
    max_file_size: int = 50 * 1024 * 1024  # Añadido para compatibilidad con main.py
    supported_formats: list = ["pdf", "txt", "docx", "xlsx", "pptx"]  # Sin puntos para compatibilidad
    ocr_enabled: bool = True
    ocr_language: str = "spa+eng"
    
    # Queue settings
    processing_queue: str = "document_processing"
    max_retries: int = 3
    retry_delay: int = 5
    
    @property
    def database_url(self) -> str:
        """Build PostgreSQL connection URL"""
        # Usar la URL del entorno si está disponible
        env_url = os.getenv("DATABASE_URL")
        if env_url:
            return env_url.replace("postgresql://", "postgresql+asyncpg://")
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def redis_url(self) -> str:
        """Build Redis connection URL"""
        # Usar la URL del entorno si está disponible
        env_url = os.getenv("REDIS_URL")
        if env_url:
            return env_url
        if self.REDACTED:
            return f"redis://:{self.REDACTED}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def rabbitmq_url(self) -> str:
        """Build RabbitMQ connection URL"""
        # Usar la URL del entorno si está disponible
        env_url = os.getenv("RABBITMQ_URL")
        if env_url:
            return env_url
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )
    
    @property
    def minio_endpoint(self) -> str:
        """Build MinIO endpoint URL"""
        # Usar el endpoint del entorno si está disponible
        env_endpoint = os.getenv("MINIO_ENDPOINT")
        if env_endpoint:
            # Si viene como "minio:9000", usarlo directamente
            return env_endpoint
        return f"{self.minio_host}:{self.minio_port}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Permitir que las variables de entorno sobrescriban los valores por defecto
        env_prefix = ""


# Create a cached instance of settings
@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export both Settings and a Config alias for compatibility
settings = get_settings()
Config = Settings  # Alias for backward compatibility


# Convenience exports
__all__ = ["Settings", "Config", "settings", "get_settings"]