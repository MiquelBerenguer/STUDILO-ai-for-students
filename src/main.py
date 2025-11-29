from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.shared.infrastructure.db import DatabasePool

# --- IMPORT NUEVO ---
# Importamos el archivo de rutas que acabamos de crear/arreglar
from src.services.learning.api import routes as learning_routes 

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Iniciando TutorIA Backend...")
    try:
        await DatabasePool.connect()
        yield
    except Exception as e:
        print(f"❌ Error crítico en el arranque: {e}")
        raise e
    finally:
        print("🛑 Apagando servicios...")
        await DatabasePool.disconnect()

app = FastAPI(
    title="TutorIA Backend",
    version="0.5.0 (Beta)",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    pool = DatabasePool.get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}

# --- CONEXIÓN DE RUTAS (ROUTERS) ---
# Aquí es donde "enchufamos" tu nuevo archivo routes.py a la app principal
app.include_router(
    learning_routes.router, 
    prefix="/api/v1/learning", # Todas las rutas empezarán por esto
    tags=["Learning Core"]     # Para agruparlas bonito en la documentación
)