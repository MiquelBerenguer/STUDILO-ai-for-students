from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "TutorIA API Gateway"
    ENVIRONMENT: str = Field(default="dev", env="ENV")

    # --- Configuración RabbitMQ ---
    # Valores por defecto que COINCIDEN con tu docker-compose.yml
    RABBITMQ_HOST: str = "tutor-ia-rabbitmq" 
    RABBITMQ_PORT: int = 5672
    
    # ¡AQUÍ ESTABA EL ERROR! Cambiamos guest por REDACTED
    RABBITMQ_USER: str = "REDACTED"  
    RABBITMQ_PASS: str = "REDACTED" # Valor default por si falla el .env
    
    # NUEVO: Virtual Host (Vital porque tu RabbitMQ usa 'tutor_ia')
    RABBITMQ_VHOST: str = "tutor_ia" 

    RABBITMQ_CONNECTION_TIMEOUT: int = 10 
    RABBITMQ_MAX_RETRIES: int = 3 
    RABBITMQ_RETRY_BACKOFF: int = 1 

    # --- Topología ---
    EXAM_EXCHANGE_NAME: str = "tutor.exams"
    EXAM_QUEUE_NAME: str = "exam.generate.job"
    EXAM_DLQ_NAME: str = "exam.generate.dlq"
    MESSAGE_TTL_MS: int = 300000 

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()