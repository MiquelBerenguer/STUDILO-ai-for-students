from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse
import structlog
import time
from contextlib import asynccontextmanager
import uuid
from typing import Dict, Optional
from datetime import datetime
import json

from .config import get_settings
from .core.database import check_database_connection, create_tables
from .core.redis_client import redis_client
from .core.minio_client import get_minio_client
from .core.rabbitmq_client import rabbitmq_client

# Configurar logging estructurado
logger = structlog.get_logger()

# Métricas de Prometheus
processed_files = Counter('processed_files_total', 'Total files processed', ['status', 'file_type'])
processing_time = Histogram('processing_duration_seconds', 'Time spent processing files')
active_jobs = Counter('active_processing_jobs', 'Number of active processing jobs')
minio_operations = Counter('minio_operations_total', 'MinIO operations', ['operation', 'status'])

# Configuración
settings = get_settings()

# Cliente MinIO (singleton)
minio_client = None

# Almacenar conexiones globales
connections = {
    "database": False,
    "redis": False,
    "minio": False,
    "rabbitmq": False
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global minio_client
    
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
            logger.info("Database connection successful")
            logger.info("Database initialized")
        
        # Redis
        await redis_client.connect()
        connections["redis"] = True
        logger.info("Redis connection successful")
        logger.info("Redis initialized")
        
        # MinIO - Usar el cliente singleton
        try:
            minio_client = get_minio_client()
            connections["minio"] = True
            logger.info("MinIO connection successful")
            logger.info("MinIO initialized")
        except Exception as e:
            logger.error(f"MinIO initialization failed: {e}")
            connections["minio"] = False
        
        # RabbitMQ
        await rabbitmq_client.connect()
        connections["rabbitmq"] = True
        logger.info("RabbitMQ connection successful")
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
        "connections": connections,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Si alguna conexión crítica falla, marcar como unhealthy
    if not all([connections["database"], connections["redis"]]):
        health_status["status"] = "degraded"
    
    if not connections["minio"]:
        health_status["status"] = "degraded"
        health_status["warnings"] = ["MinIO connection failed - files will not be persisted"]
    
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
        if not file.filename:
            raise HTTPException(400, "No filename provided")
            
        # Leer contenido del archivo para obtener el tamaño real
        file_content = await file.read()
        file_size = len(file_content)
        
        # Validar tamaño
        max_size = getattr(settings, 'max_file_size', 10 * 1024 * 1024)  # 10MB default
        if file_size > max_size:
            raise HTTPException(400, f"File too large. Max size: {max_size} bytes")
        
        # Obtener extensión
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else 'unknown'
        supported_formats = getattr(settings, 'supported_formats', ['pdf', 'doc', 'docx', 'txt'])
        
        if file_extension not in supported_formats:
            raise HTTPException(400, f"Unsupported format. Supported: {supported_formats}")
        
        logger.info("Processing file", 
                   filename=file.filename,
                   size=file_size,
                   type=file_extension,
                   job_id=job_id)
        
        # Preparar rutas en MinIO
        object_name = f"{job_id}/{file.filename}"
        minio_path = None
        
        # Subir archivo a MinIO
        if connections["minio"] and minio_client:
            try:
                # Preparar metadata
                metadata = {
                    'job-id': job_id,
                    'filename': file.filename,
                    'size': str(file_size),
                    'content-type': file.content_type or 'application/octet-stream',
                    'upload-time': datetime.utcnow().isoformat()
                }
                
                # Subir archivo
                upload_result = minio_client.upload_file(
                    file_data=file_content,
                    object_name=object_name,
                    bucket_name='uploads',
                    metadata=metadata
                )
                
                minio_path = f"uploads/{object_name}"
                logger.info("File uploaded to MinIO", 
                          bucket=upload_result['bucket'],
                          object_name=upload_result['object_name'],
                          size=upload_result['size'])
                
                minio_operations.labels(operation="upload", status="success").inc()
                
            except Exception as e:
                logger.error(f"MinIO upload failed: {e}", job_id=job_id)
                minio_operations.labels(operation="upload", status="error").inc()
                # Continuar sin MinIO (opcional: podrías hacer esto obligatorio)
        else:
            logger.warning("MinIO not available, file will not be persisted", job_id=job_id)
        
        # Crear job en Redis
        job_data = {
            "job_id": job_id,
            "filename": file.filename,
            "size": file_size,
            "type": file_extension,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
            "progress": 0,
            "minio_path": minio_path,  # Guardar la ruta de MinIO
            "content_type": file.content_type
        }
        
        if connections["redis"]:
            await redis_client.set_job_status(job_id, job_data)
            logger.info("Job status saved to Redis", job_id=job_id)
        
        # Preparar mensaje para RabbitMQ
        task_data = {
            "job_id": job_id,
            "filename": file.filename,
            "minio_object_key": object_name,  # Clave para que el worker descargue de MinIO
            "minio_bucket": "uploads",
            "user_id": "anonymous",  # TODO: Obtener del contexto de autenticación
            "require_analysis": True,
            "created_at": datetime.utcnow().isoformat(),
            "metadata": {
                "size": file_size,
                "type": file_extension,
                "content_type": file.content_type or 'application/octet-stream',
                "original_filename": file.filename
            }
        }
        
        # Publicar tarea en RabbitMQ
        if connections["rabbitmq"]:
            # Determinar prioridad basada en el tamaño
            priority = "high" if file_size < 1024 * 1024 else "normal"  # <1MB = alta prioridad
            
            await rabbitmq_client.publish_task(task_data)
            logger.info("Task published to queue", 
                       job_id=job_id,
                       priority=priority,
                       queue="pdf.process")
        
        # Registrar métricas
        processed_files.labels(status="queued", file_type=file_extension).inc()
        processing_time.observe(time.time() - start_time)
        active_jobs.inc()
        
        return {
            "job_id": job_id,
            "status": "queued",
            "filename": file.filename,
            "size": file_size,
            "minio_path": minio_path,
            "message": "File uploaded and queued for processing",
            "check_status_url": f"/status/{job_id}",
            "estimated_time": f"{file_size / (1024 * 1024) * 10:.0f} seconds"  # Estimación básica
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
            # Agregar información adicional si el archivo está en MinIO
            if job_data.get("minio_path") and connections["minio"] and minio_client:
                try:
                    # Verificar si el archivo existe en MinIO
                    object_name = f"{job_id}/{job_data.get('filename')}"
                    file_info = minio_client.get_file_info(object_name, 'uploads')
                    if file_info:
                        job_data["storage_info"] = {
                            "available": True,
                            "size": file_info['size'],
                            "last_modified": file_info['last_modified']
                        }
                except Exception as e:
                    logger.error(f"Error checking MinIO file: {e}")
            
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
        "timestamp": datetime.utcnow().isoformat(),
        "status": "operational" if connections["rabbitmq"] else "disconnected"
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
            job_data["cancelled_at"] = datetime.utcnow().isoformat()
            await redis_client.set_job_status(job_id, job_data)
            
            # Opcional: Eliminar archivo de MinIO
            if job_data.get("minio_path") and connections["minio"] and minio_client:
                try:
                    object_name = f"{job_id}/{job_data.get('filename')}"
                    minio_client.delete_file(object_name, 'uploads')
                    logger.info(f"Deleted file from MinIO: {object_name}")
                except Exception as e:
                    logger.error(f"Error deleting file from MinIO: {e}")
            
            active_jobs.dec()
            
            return {
                "message": f"Job {job_id} cancelled",
                "job_id": job_id,
                "status": "cancelled"
            }
    
    raise HTTPException(404, f"Job {job_id} not found")

@app.get("/storage/list")
async def list_stored_files(prefix: Optional[str] = None):
    """
    Listar archivos almacenados en MinIO (endpoint de debug/admin)
    """
    if not connections["minio"] or not minio_client:
        raise HTTPException(503, "MinIO service not available")
    
    try:
        files = minio_client.list_files('uploads', prefix=prefix or '')
        return {
            "total": len(files),
            "files": files,
            "bucket": "uploads"
        }
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(500, f"Error listing files: {str(e)}")