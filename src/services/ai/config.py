from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache

class AISettings(BaseSettings):
    """
    Configuración inmutable del servicio de IA.
    Lee variables de entorno (.env) automáticamente.
    """
    # Infraestructura (Credenciales)
    openai_api_key: str = Field(..., description="Key obligatoria. Si falta, la app no arranca.")
    
    # Modelo (Usamos tu versión específica para estabilidad en JSON)
    openai_model: str = Field(default="gpt-4o-2024-08-06", description="Modelo con soporte Structured Outputs")
    
    # Hiperparámetros (Control de comportamiento global)
    openai_temperature: float = Field(default=0.1, description="Baja temperatura = Más precisión matemática")
    
    # Resiliencia (Tenacity)
    max_retries: int = Field(default=3, description="Intentos de reconexión con OpenAI")
    retry_min_wait: int = Field(default=2, description="Segundos de espera mínima entre reintentos")

    # Configuración Pydantic V2 (Moderna)
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore", # Ignora variables extra del .env (como DB_HOST)
        case_sensitive=False # Permite usar OPENAI_API_KEY en .env y mapearlo a openai_api_key
    )

@lru_cache()
def get_ai_settings() -> AISettings:
    """
    Singleton con caché. 
    Se instancia una sola vez para no leer el disco (.env) en cada petición.
    """
    return AISettings()