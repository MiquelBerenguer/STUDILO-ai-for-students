import redis.asyncio as redis
from redis.asyncio.sentinel import Sentinel
from typing import Optional, Any
import json
import structlog
from ..config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class RedisClient:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.sentinel: Optional[Sentinel] = None
        
    async def connect(self):
        """Inicializar conexión a Redis vía Sentinel para HA"""
        try:
            logger.info("Connecting to Redis via Sentinel...", 
                        sentinel_host=settings.redis_sentinel_host, 
                        master_set=settings.redis_master_set)

            # 1. Definir nodos Sentinel (en nuestro caso, 1 nodo, pero es una lista)
            sentinel_nodes = [(settings.redis_sentinel_host, settings.redis_sentinel_port)]
            
            # 2. Configurar cliente Sentinel
            # Usamos el mismo password para Sentinel y Redis por simplicidad en este setup
            self.sentinel = Sentinel(
                sentinel_nodes,
                sentinel_kwargs={"password": settings.REDACTED}
            )

            # 3. Obtener el master actual desde Sentinel
            # Esto devuelve un cliente Redis asíncrono configurado para el master actual
            self.redis = self.sentinel.master_for(
                settings.redis_master_set,
                password=settings.REDACTED,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                retry_on_timeout=True,
                health_check_interval=30
            )

            # 4. Verificar conexión real haciendo un PING al master
            await self.redis.ping()
            logger.info("✅ Redis HA connection successful (via Sentinel)")
            
        except Exception as e:
            logger.error("❌ Redis Sentinel connection failed", error=str(e))
            # Es crítico: si falla el caché/cola, puede que debamos detener el servicio
            raise

    async def disconnect(self):
        """Cerrar conexión a Redis"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")

    # --- MÉTODOS HELPER (Sin cambios en la lógica, solo usan self.redis) ---
    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self.redis.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error("Redis get error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        try:
            serialized = json.dumps(value)
            await self.redis.setex(key, expire, serialized)
            return True
        except Exception as e:
            logger.error("Redis set error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error("Redis delete error", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error("Redis exists error", key=key, error=str(e))
            return False

    async def set_job_status(self, job_id: str, status: dict, expire: int = 86400):
        key = f"job:status:{job_id}"
        await self.set(key, status, expire)

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        key = f"job:status:{job_id}"
        return await self.get(key)

    async def increment_counter(self, key: str) -> int:
        try:
            return await self.redis.incr(key)
        except Exception as e:
            logger.error("Redis increment error", key=key, error=str(e))
            return 0

# Instancia global
redis_client = RedisClient()