import time
import uuid
import logging
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.rabbitmq import mq_client 

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API-Gateway")

# --- Modelos de Datos (Contratos) ---
class ExamRequest(BaseModel):
    topic: str = Field(..., min_length=3, example="Termodinámica Aplicada")
    difficulty: str = Field(..., pattern="^(easy|medium|hard)$", example="hard")

class ExamResponse(BaseModel):
    task_id: str
    status: str
    message: str

# --- Lifespan (Ciclo de Vida) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await mq_client.connect()
    except Exception as e:
        logger.error(f"⚠️ El Gateway arrancó sin RabbitMQ: {e}")
    yield
    # Shutdown
    await mq_client.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    # Verificamos estado real de la conexión
    is_connected = mq_client.connection and not mq_client.connection.is_closed
    return {
        "status": "healthy", 
        "rabbitmq": "connected" if is_connected else "disconnected"
    }

# --- ENDPOINT PRINCIPAL (TAREA 4.1) ---
@app.post(
    "/exams/generate", 
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ExamResponse
)
async def request_exam_generation(request: ExamRequest):
    """
    Endpoint Asíncrono:
    1. Recibe parámetros.
    2. Genera ID único.
    3. Encola en RabbitMQ con fiabilidad.
    """
    task_id = str(uuid.uuid4())
    created_at = time.time()

    payload = {
        "task_id": task_id,
        "action": "generate_exam",
        "topic": request.topic,
        "difficulty": request.difficulty,
        "created_at": created_at,
        "origin": "api-gateway"
    }
    
    # Enviamos al broker
    success = await mq_client.send_message(payload)
    
    if not success:
        # Si tras los reintentos falla, damos error 503
        logger.error(f"Fallo al encolar tarea {task_id}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="El sistema de procesamiento está saturado o no disponible."
        )
        
    logger.info(f"Tarea {task_id} encolada exitosamente.")
    
    return {
        "task_id": task_id,
        "status": "queued", 
        "message": "Solicitud aceptada. Procesando..."
    }