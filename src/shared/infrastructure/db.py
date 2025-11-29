import os
import asyncpg
import ssl
from typing import Optional

class DatabasePool:
    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def connect(cls):
        """
        Inicializa el Pool de conexiones.
        CALIDAD: Detecta si necesitamos SSL basándose en variables de entorno.
        """
        if cls._pool is None:
            try:
                # Construimos la DSN
                dsn = (
                    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
                    f"@{os.getenv('POSTGRES_HOST', 'postgres-master')}:5432/{os.getenv('POSTGRES_DB')}"
                )
                
                # LÓGICA DE PRODUCCIÓN VS DESARROLLO
                # Leemos una variable nueva: DB_USE_SSL
                # Si es "true", creamos un contexto seguro. Si no, desactivamos SSL.
                use_ssl = os.getenv("DB_USE_SSL", "false").lower() == "true"
                
                ssl_context = None
                if use_ssl:
                    # Configuración PRO (AWS/Production)
                    # Crea un contexto SSL por defecto que valida certificados
                    ssl_context = ssl.create_default_context()
                    print("🔒 Modo Seguro: SSL Activado")
                else:
                    # Configuración DEV (Localhost/Docker)
                    ssl_context = False
                    print("🔓 Modo Desarrollo: SSL Desactivado")

                print(f"🔌 Conectando a Base de Datos: {os.getenv('POSTGRES_HOST')}...")
                
                cls._pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                    ssl=ssl_context # Inyectamos la decisión inteligente aquí
                )
                print("✅ Database Pool conectado exitosamente.")
            except Exception as e:
                print(f"❌ Error fatal conectando a DB: {e}")
                raise e

    @classmethod
    async def disconnect(cls):
        if cls._pool:
            await cls._pool.close()
            print("💤 Database Pool cerrado.")

    @classmethod
    def get_pool(cls) -> asyncpg.Pool:
        if cls._pool is None:
            raise RuntimeError("La base de datos no ha sido inicializada.")
        return cls._pool