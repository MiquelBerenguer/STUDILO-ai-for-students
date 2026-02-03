import os
import json
import uuid
import aio_pika
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from minio import Minio

# --- SEGURIDAD ---
# Importamos la dependencia que valida el Token JWT
from app.dependencies import get_current_user
# Si quieres tipado estricto, importa tu modelo de User, si no, lo tratamos como objeto genérico
# from src.shared.database.models import User 

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

# --- CONFIGURACIÓN ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_USER = os.getenv("MINIO_USER", "REDACTED")
MINIO_PASSWORD = os.getenv("MINIO_PASSWORD", "REDACTED")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://REDACTED:REDACTED@rabbitmq:5672/tutor_ia")

# Cliente MinIO
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_USER,
    secret_key=MINIO_PASSWORD,
    secure=False
)

# Fail-safe bucket creation
try:
    if not minio_client.bucket_exists("uploads"):
        minio_client.make_bucket("uploads")
except Exception as e:
    print(f"⚠️ Aviso MinIO: {e}")

@router.post("/upload", summary="Subir apuntes (PDF)")
async def upload_document(
    file: UploadFile = File(...),
    course_id: str = Form(..., description="ID del curso (ej: fisica_1)"),
    university_id: str = Form("general", description="ID de la universidad"),
    # 🔒 EL GUARDIÁN: Si no hay token válido, esto lanza 401 Unauthorized automáticamente
    current_user = Depends(get_current_user) 
):
    """
    Sube apuntes al sistema RAG.
    Requiere autenticación JWT (Bearer Token).
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    job_id = str(uuid.uuid4())
    safe_filename = file.filename.replace(" ", "_")
    file_extension = safe_filename.split('.')[-1]
    object_name = f"{job_id}.{file_extension}"

    try:
        # 1. Subir a MinIO
        minio_client.put_object(
            "uploads",
            object_name,
            file.file,
            length=-1,
            part_size=10*1024*1024
        )

        # 2. Encolar tarea
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            
            message_body = {
                "job_id": job_id,
                "filename": safe_filename,
                "minio_bucket": "uploads",
                "minio_object_key": object_name,
                "course_id": course_id,
                "university_id": university_id,
                "status": "queued",
                "doc_type": "notes",
                # Añadimos quién subió el archivo para auditoría futura
                "user_id": str(current_user.id) if hasattr(current_user, 'id') else "unknown"
            }

            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(message_body).encode()),
                routing_key="pdf.process.engineering"
            )

        return {
            "status": "success",
            "job_id": job_id,
            "message": "Archivo seguro recibido. El Profesor lo está leyendo."
        }

    except Exception as e:
        print(f"❌ Error en upload: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")