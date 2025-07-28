from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse
import structlog
import time
from contextlib import asynccontextmanager
import uuid
from typing import Dict

from .config import get_settings
from .core.database import check_database_connection, create_tables
from .core.redis_client import redis_client
from .core.minio_client import minio_client
from .core.rabbitmq_client import rabbitmq_client

# Configurar logging estructurado
logger = structlog.get_logger()

# Métricas de Prometheus
processed_files = Counter('processed_files_total', 'Total files processed', ['status', 'file_type'])
processing_time = Histogram('processing_duration_seconds', 'Time spent processing files')
active_jobs = Counter('active_processing_jobs', 'Number of active processing jobs')

# Configuración
settings = get_settings()

# Almacenar conexiones globales
connections = {
    "database": False,
    "redis": False,
    "minio": False,
    "rabbitmq": False
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting processor service", 
                service=settings.service_name,
                port=settings.service_port)
    
    # Inicializar conexiones
    try:
        # Database
        if await check_database_connection():
            await create_tables()
            connections["database"] = True
            logger.info("Database initialized")
        
        # Redis
        await redis_client.connect()
        connections["redis"] = True
        logger.info("Redis initialized")
        
        # MinIO
        await minio_client.connect()
        connections["minio"] = True
        logger.info("MinIO initialized")
        
        # RabbitMQ
        await rabbitmq_client.connect()
        connections["rabbitmq"] = True
        logger.info("RabbitMQ initialized")
        
    except Exception as e:
        logger.error("Failed to initialize services", error=str(e))
        # Continuar aunque algún servicio falle
    
    yield
    
    # Shutdown
    logger.info("Shutting down processor service")
    
    # Cerrar conexiones
    try:
        await redis_client.disconnect()
        await rabbitmq_client.disconnect()
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))

# Crear aplicación FastAPI
app = FastAPI(
    title="Document Processor Service",
    version="1.0.0",
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Check health status of the service and its dependencies"""
    health_status = {
        "status": "healthy",
        "service": settings.service_name,
        "version": "1.0.0",
        "connections": connections
    }
    
    # Si alguna conexión crítica falla, marcar como unhealthy
    if not all([connections["database"], connections["redis"]]):
        health_status["status"] = "degraded"
    
    return health_status

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.post("/process")
async def process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Endpoint principal para procesar documentos
    """
    start_time = time.time()
    job_id = str(uuid.uuid4())
    
    try:
        # Validar archivo
        if file.size > settings.max_file_size:
            raise HTTPException(400, f"File too large. Max size: {settings.max_file_size} bytes")
        
        # Obtener extensión
        file_extension = file.filename.split('.')[-1].lower()
        if file_extension not in settings.supported_formats:
            raise HTTPException(400, f"Unsupported format. Supported: {settings.supported_formats}")
        
        logger.info("Processing file", 
                   filename=file.filename,
                   size=file.size,
                   type=file_extension,
                   job_id=job_id)
        
        # Leer contenido del archivo
        file_content = await file.read()
        
        # Subir archivo a MinIO
        if connections["minio"]:
            try:
                import io
                file_data = io.BytesIO(file_content)
                object_name = f"uploads/{job_id}/{file.filename}"
                await minio_client.upload_file(
                    object_name,
                    file_data,
                    content_type=file.content_type
                )
                logger.info("File uploaded to MinIO", object_name=object_name)
            except Exception as e:
                logger.error("MinIO upload failed", error=str(e))
        
        # Crear job en Redis
        if connections["redis"]:
            job_data = {
                "job_id": job_id,
                "filename": file.filename,
                "size": file.size,
                "type": file_extension,
                "status": "queued",
                "created_at": time.time(),
                "progress": 0
            }
            await redis_client.set_job_status(job_id, job_data)
        
        # Publicar tarea en RabbitMQ
        if connections["rabbitmq"]:
            task_data = {
                "job_id": job_id,
                "filename": file.filename,
                "object_name": f"uploads/{job_id}/{file.filename}",
                "file_type": file_extension,
                "created_at": time.time()
            }
            await rabbitmq_client.publish_task(task_data)
            logger.info("Task published to queue", job_id=job_id)
        
        # Registrar métricas
        processed_files.labels(status="queued", file_type=file_extension).inc()
        processing_time.observe(time.time() - start_time)
        active_jobs.inc()
        
        return {
            "job_id": job_id,
            "status": "queued",
            "filename": file.filename,
            "message": "File queued for processing",
            "check_status_url": f"/status/{job_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing file", error=str(e), job_id=job_id)
        processed_files.labels(status="error", file_type="unknown").inc()
        raise HTTPException(500, f"Processing error: {str(e)}")

@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Verificar el estado de un trabajo de procesamiento
    """
    # Buscar en Redis
    if connections["redis"]:
        job_data = await redis_client.get_job_status(job_id)
        if job_data:
            return job_data
    
    # Si no está en Redis, no existe
    raise HTTPException(404, f"Job {job_id} not found")

@app.get("/queue/size")
async def get_queue_size():
    """
    Obtener tamaño de la cola de procesamiento
    """
    size = 0
    if connections["rabbitmq"]:
        size = await rabbitmq_client.get_queue_size()
    
    return {
        "queue_size": size,
        "timestamp": time.time()
    }

@app.delete("/job/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancelar un trabajo de procesamiento
    """
    if connections["redis"]:
        job_data = await redis_client.get_job_status(job_id)
        if job_data:
            job_data["status"] = "cancelled"
            job_data["cancelled_at"] = time.time()
            await redis_client.set_job_status(job_id, job_data)
            
            active_jobs.dec()
            
            return {"message": f"Job {job_id} cancelled"}
    
    raise HTTPException(404, f"Job {job_id} not found")
