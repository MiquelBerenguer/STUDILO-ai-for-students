import redis.asyncio as redis
from typing import Optional, Any
import json
import structlog
from ..config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class RedisClient:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        
    async def connect(self):
        """Inicializar conexión a Redis"""
        try:
            self.redis = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
                health_check_interval=30,
                socket_keepalive=True,
                retry_on_timeout=True,
            )
            # Verificar conexión
            await self.redis.ping()
            logger.info("Redis connection successful")
        except Exception as e:
            logger.error("Redis connection failed", error=str(e))
            raise
    
    async def disconnect(self):
        """Cerrar conexión a Redis"""
        if self.redis:
            await self.redis.close()
            
    async def get(self, key: str) -> Optional[Any]:
        """Obtener valor del cache"""
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("Redis get error", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        """Guardar valor en cache con expiración"""
        try:
            serialized = json.dumps(value)
            await self.redis.setex(key, expire, serialized)
            return True
        except Exception as e:
            logger.error("Redis set error", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """Eliminar clave del cache"""
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error("Redis delete error", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """Verificar si existe una clave"""
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error("Redis exists error", key=key, error=str(e))
            return False
    
    async def set_job_status(self, job_id: str, status: dict, expire: int = 86400):
        """Guardar estado de un trabajo de procesamiento"""
        key = f"job:status:{job_id}"
        await self.set(key, status, expire)
    
    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """Obtener estado de un trabajo"""
        key = f"job:status:{job_id}"
        return await self.get(key)
    
    async def increment_counter(self, key: str) -> int:
        """Incrementar un contador"""
        try:
            return await self.redis.incr(key)
        except Exception as e:
            logger.error("Redis increment error", key=key, error=str(e))
            return 0

# Instancia global
redis_client = RedisClient()