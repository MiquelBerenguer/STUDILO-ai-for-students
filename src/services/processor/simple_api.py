#!/usr/bin/env python3
"""
Simple API for File Upload
Endpoint simple para subir archivos al sistema de colas
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime
import os

# Importar el productor que ya funciona
from producers.queue_producer import QueueProducer

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(title="Simple File Upload API", version="1.0.0")

# Inicializar productor
producer = QueueProducer()

# Base de datos simulada para almacenar estados de trabajos
jobs_db = {}

# Modelo para actualizar estado
class StatusUpdate(BaseModel):
    status: str
    result: dict = None
    error: str = None

@app.on_event("startup")
async def startup_event():
    """Inicializar conexiones al arrancar"""
    try:
        if producer.connect():
            logger.info("✅ Conectado a RabbitMQ")
        else:
            logger.error("❌ No se pudo conectar a RabbitMQ")
    except Exception as e:
        logger.error(f"❌ Error en startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cerrar conexiones al apagar"""
    producer.close()
    logger.info("🔌 Conexiones cerradas")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "simple-upload-api",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Endpoint para subir archivos al sistema de colas
    
    Args:
        file: Archivo a procesar
        
    Returns:
        JSON con job_id y estado
    """
    try:
        # Validar archivo
        if not file.filename:
            raise HTTPException(status_code=400, detail="No se proporcionó archivo")
        
        # Generar job_id
        job_id = str(uuid.uuid4())
        
        # Crear ruta del archivo (simulada)
        file_path = f"uploads/{job_id}/{file.filename}"
        
        # Obtener metadata del archivo
        file_content = await file.read()
        file_size = len(file_content)
        
        # Guardar estado inicial en la base de datos simulada
        jobs_db[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "filename": file.filename,
            "created_at": datetime.utcnow().isoformat(),
            "file_size": file_size,
            "result": None,
            "error": None
        }
        
        # Enviar a la cola usando el productor que ya funciona
        try:
            producer.send_pdf_processing_job(
                filename=file.filename,
                file_path=file_path,
                user_id="anonymous",  # TODO: Obtener del contexto de autenticación
                priority=False,
                require_analysis=True,
                metadata={
                    "size_bytes": file_size,
                    "content_type": file.content_type,
                    "upload_timestamp": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"✅ Archivo enviado a cola: {file.filename} (Job ID: {job_id})")
            
            return JSONResponse(
                status_code=200,
                content={
                    "job_id": job_id,
                    "status": "queued",
                    "filename": file.filename,
                    "message": "Archivo enviado a procesamiento",
                    "estimated_time": 30  # segundos estimados
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error enviando a cola: {e}")
            raise HTTPException(status_code=500, detail=f"Error enviando a cola: {e}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error procesando archivo: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {e}")

@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Consultar el estado de un trabajo
    
    Args:
        job_id: ID del trabajo
        
    Returns:
        Estado del trabajo
    """
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    
    return jobs_db[job_id]

@app.get("/result/{job_id}")
async def get_job_result(job_id: str):
    """
    Obtener el resultado del procesamiento de un trabajo
    
    Args:
        job_id: ID del trabajo
        
    Returns:
        Resultado del procesamiento
    """
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    
    job = jobs_db[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job aún no completado. Estado: {job['status']}")
    
    if not job["result"]:
        raise HTTPException(status_code=404, detail="No hay resultado disponible")
    
    return {
        "job_id": job_id,
        "filename": job["filename"],
        "status": job["status"],
        "result": job["result"],
        "processed_at": job.get("processed_at")
    }

@app.post("/update_status/{job_id}")
async def update_job_status_endpoint(job_id: str, status_update: StatusUpdate):
    """
    Endpoint para actualizar el estado de un trabajo.
    Usado por los workers para informar el estado de un trabajo.
    """
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    
    update_job_status(job_id, status_update.status, status_update.result, status_update.error)
    
    return {"message": f"Job {job_id} actualizado a {status_update.status}"}

# Función para actualizar el estado de los trabajos (llamada por los workers)
def update_job_status(job_id: str, status: str, result: dict = None, error: str = None):
    """Actualizar el estado de un job (usado por los workers)"""
    if job_id in jobs_db:
        jobs_db[job_id]["status"] = status
        jobs_db[job_id]["updated_at"] = datetime.utcnow().isoformat()
        if result:
            jobs_db[job_id]["result"] = result
            jobs_db[job_id]["processed_at"] = datetime.utcnow().isoformat()
        if error:
            jobs_db[job_id]["error"] = error
        logger.info(f"📊 Job {job_id} actualizado: {status}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
