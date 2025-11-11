#!/usr/bin/env python3
"""
PDF Processing Worker - V4.0 (R#7 Implementado)
- R#5: Actualización de estado en Redis
- R#8: Alta Disponibilidad con Redis Sentinel
- R#7: Implementación de Chunking con Langchain
"""

import pika
import json
import time
import logging
import os
import sys
from typing import Dict, Any, Optional
import traceback
import threading
from datetime import datetime
import io
import tempfile
from pathlib import Path

# --- Imports de Redis ---
try:
    from redis.sentinel import Sentinel
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("⚠️ Librería 'redis' no encontrada. El estado NO se actualizará.")

# Importar MinIO
try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    logging.warning("MinIO no disponible - funcionando en modo degradado")

# Importar librerías para OCR
try:
    import PyPDF2
    from pdf2image import convert_from_bytes
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError as e:
    OCR_AVAILABLE = False
    logging.warning(f"OCR no disponible: {e}")

# Importar librerías para Chunking (R#7)
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    logging.warning(f"Chunking no disponible (langchain): {e}")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MinIOHelper:
    """Helper class para operaciones con MinIO"""
    
    def __init__(self):
        # FIX: Inicializar siempre self.client a None primero
        self.client = None
        if MINIO_AVAILABLE:
            try:
                self.endpoint = os.getenv('MINIO_ENDPOINT', 'minio:9000')
                self.access_key = os.getenv('MINIO_USER', 'REDACTED')
                self.secret_key = os.getenv('MINIO_PASSWORD', 'REDACTED')
                
                self.client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=False
                )
                logger.info(f"✅ MinIO conectado: {self.endpoint}")
            except Exception as e:
                logger.error(f"❌ Error conectando a MinIO: {e}")
                self.client = None
    
    def download_file(self, bucket: str, object_name: str) -> Optional[bytes]:
        """Descarga archivo de MinIO"""
        if not self.client:
            logger.error("❌ Intento de descarga sin cliente MinIO inicializado")
            return None
        
        try:
            response = self.client.get_object(bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            logger.info(f"📥 Descargado de MinIO: {bucket}/{object_name} ({len(data)} bytes)")
            return data
        except Exception as e:
            logger.error(f"❌ Error descargando de MinIO: {e}")
            return None
    
    def upload_file(self, bucket: str, object_name: str, data: bytes) -> bool:
        """Sube archivo a MinIO"""
        if not self.client:
            return False
        
        try:
            data_stream = io.BytesIO(data)
            self.client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=data_stream,
                length=len(data)
            )
            logger.info(f"📤 Subido a MinIO: {bucket}/{object_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Error subiendo a MinIO: {e}")
            return False

class PDFWorkerMultiQueue:
    def __init__(self, rabbitmq_url: str = None):
        """Inicializa el worker con RabbitMQ, MinIO y Redis HA"""
        self.rabbitmq_url = rabbitmq_url or os.getenv(
            'RABBITMQ_URL',
            'amqp://REDACTED:REDACTED@rabbitmq:5672/tutor_ia'
        )
        self.connection = None
        self.channel = None
        self.consumer_tags = {}
        
        # Inicializar MinIO
        self.minio = MinIOHelper()

        # --- INICIO REFACTOR R#7: Inicializar Text Splitter ---
        self.text_splitter = None
        if LANGCHAIN_AVAILABLE:
            try:
                # Parámetros (idealmente de env vars, pero definidos aquí por claridad)
                # Tarea 2.4: Trozos de ~1000 tokens (aprox 4000 chars) con solapamiento
                chunk_size = int(os.getenv('CHUNK_SIZE', 4000))
                chunk_overlap = int(os.getenv('CHUNK_OVERLAP', 400))

                self.text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    length_function=len,
                    is_separator_regex=False,
                    separators=["\n\n", "\n", ". ", " ", ""] # Separadores semánticos
                )
                logger.info(f"✅ Chunking (R#7) habilitado (Size: {chunk_size}, Overlap: {chunk_overlap})")
            except Exception as e:
                logger.error(f"❌ Error inicializando TextSplitter: {e}")
                self.text_splitter = None
        # --- FIN REFACTOR R#7 ---
        
        # --- FIX R#5/R#8 V3.3: Inicialización Redis Sentinel ROBUSTA ---
        self.redis_master = None
        if REDIS_AVAILABLE:
            try:
                sentinel_host = os.getenv('REDIS_SENTINEL_HOST', 'redis-sentinel')
                sentinel_port = int(os.getenv('REDIS_SENTINEL_PORT', 26379))
                master_set = os.getenv('REDIS_MASTER_SET', 'tutormaster')
                REDACTED = os.getenv('REDIS_PASSWORD', None)

                logger.info(f"🔧 Configurando Redis Sentinel: {sentinel_host}:{sentinel_port}")

                # FIX V3.3: Usar sentinel_kwargs para la autenticación de Sentinel
                sentinel_kwargs = {'password': REDACTED} if REDACTED else {}

                sentinel = Sentinel(
                    [(sentinel_host, sentinel_port)],
                    sentinel_kwargs=sentinel_kwargs, # <--- CLAVE AQUÍ
                    socket_timeout=1.0
                )
                
                # Obtenemos el master
                self.redis_master = sentinel.master_for(
                    master_set,
                    password=REDACTED, # Contraseña para el nodo Redis real
                    socket_timeout=1.0,
                    decode_responses=True
                )
                
                # Prueba de conexión INMEDIATA para fallar rápido si está mal
                self.redis_master.ping()
                logger.info(f"✅ Redis HA conectado y autenticado correctamente")
            except Exception as e:
                logger.error(f"❌ Error inicializando Redis HA: {e}")
                # Si falla aquí, self.redis_master será None y el worker seguirá sin actualizar estado
        # ------------------------------------------------------------

        self.queues = ['pdf.process.priority', 'pdf.process']
        if OCR_AVAILABLE:
            logger.info("✅ OCR disponible con Tesseract")
        
    def connect(self):
        """Establece conexión con RabbitMQ"""
        try:
            parameters = pika.URLParameters(self.rabbitmq_url)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.basic_qos(prefetch_count=1)
            logger.info("✅ Conectado a RabbitMQ")
            return True
        except Exception as e:
            logger.error(f"❌ Error conectando a RabbitMQ: {e}")
            return False
            
    def extract_text_from_pdf(self, pdf_content: bytes, filename: str) -> tuple[str, int, bool]:
        text_extracted = ""
        pages_count = 0
        ocr_used = False
        if not OCR_AVAILABLE: return "OCR no disponible", 0, False
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_file.flush()
                tmp_path = tmp_file.name
            try:
                logger.info(f"📖 Extrayendo texto de {filename}...")
                with open(tmp_path, 'rb') as pdf_file:
                    pdf = PyPDF2.PdfReader(pdf_file)
                    pages_count = len(pdf.pages)
                    for p in pdf.pages: text_extracted += p.extract_text() or ""
                if len(text_extracted.strip()) < 100 and pages_count > 0:
                    logger.info("🔍 Aplicando OCR...")
                    ocr_used = True
                    images = convert_from_bytes(pdf_content, dpi=200, first_page=1, last_page=min(5, pages_count))
                    text_extracted = ""
                    for img in images: text_extracted += pytesseract.image_to_string(img, lang='spa+eng') + "\n"
            finally:
                if os.path.exists(tmp_path): os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"❌ Error procesando PDF: {e}")
            text_extracted = f"Error: {str(e)}"
        return text_extracted, pages_count, ocr_used

    def process_pdf(self, pdf_data: Dict[str, Any]) -> Dict[str, Any]:
        job_id = pdf_data.get('job_id', 'unknown')
        filename = pdf_data.get('filename', 'unknown.pdf')
        start_time = time.time()
        logger.info(f"📄 Procesando PDF: {filename} (Job: {job_id})")

        pdf_content = None
        if pdf_data.get('minio_object_key'):
             # FIX: Asegurar que self.minio está inicializado
             if self.minio and self.minio.client:
                 pdf_content = self.minio.download_file(
                     pdf_data.get('minio_bucket', 'uploads'), 
                     pdf_data.get('minio_object_key')
                 )
             else:
                 logger.error("❌ No se puede descargar: MinIO no disponible")

        # --- INICIO REFACTOR R#7 ---
        chunks = []
        num_chunks = 0
        status = 'failed' # Asumir fallo hasta que se pruebe lo contrario
        # --- FIN REFACTOR R#7 ---

        if pdf_content:
            text, pages, ocr = self.extract_text_from_pdf(pdf_content, filename)
            status = 'completed' if not text.startswith("Error:") else 'failed'
        else:
            text, pages, ocr = "Error: No se pudo descargar archivo", 0, False
            status = 'failed'

        # --- INICIO REFACTOR R#7: Aplicar Chunking ---
        if status == 'completed' and self.text_splitter:
            try:
                logger.info(f"🧩 Aplicando Chunking (R#7) para Job {job_id}...")
                chunks = self.text_splitter.split_text(text)
                num_chunks = len(chunks)
                logger.info(f"🧩 Texto dividido en {num_chunks} chunks para Job {job_id}")
            except Exception as e:
                logger.error(f"❌ Error durante el chunking: {e}")
                status = 'failed_chunking' # Nuevo estado de error
                text = f"Error en Chunking: {e}" # Actualizar texto para reflejar error
        elif status == 'completed' and not self.text_splitter:
            logger.warning("⚠️ Worker completó extracción pero TextSplitter no está disponible. Saltando chunking.")
            status = 'completed_no_chunks' # Nuevo estado
        # --- FIN REFACTOR R#7 ---

        processing_time = time.time() - start_time
        result = {
            'status': status,
            'job_id': job_id,
            # 'text_preview': text[:200] + "...", # R#7: Eliminado, 'text' puede ser un error
            'text_length': len(text) if status != 'failed_chunking' else 0,
            'pages': pages,
            'ocr_used': ocr,
            'num_chunks': num_chunks, # R#7: Nuevo campo clave
            'processing_time': processing_time,
            'processed_at': datetime.utcnow().isoformat()
        }

        # --- INICIO REFACTOR R#7: Lógica de guardado en MinIO ---
        if self.minio and self.minio.client and pdf_content:
             # 1. Guardar el JSON de resultado/metadata (siempre)
             self.minio.upload_file(
                 'processed', 
                 f"{job_id}/result.json", 
                 json.dumps(result).encode('utf-8')
             )
             
             # 2. Guardar los chunks (solo si se generaron)
             if num_chunks > 0:
                 chunks_data = json.dumps(chunks).encode('utf-8')
                 self.minio.upload_file(
                     'processed', 
                     f"{job_id}/chunks.json", # Nuevo archivo
                     chunks_data
                 )
                 logger.info(f"📤 Subidos {num_chunks} chunks a MinIO como 'chunks.json'")

             # 3. YA NO GUARDAMOS el full_text.txt
             # if text: self.minio.upload_file('processed', f"{job_id}/full_text.txt", text.encode('utf-8'))
        # --- FIN REFACTOR R#7 ---

        return result

    def update_job_status(self, job_id: str, result: Dict[str, Any]):
        """Actualiza Redis con manejo de errores robusto"""
        if not self.redis_master:
            # Si falló la conexión al inicio, no intentamos cada vez
            return

        try:
            redis_key = f"job:{job_id}"
            current_data_raw = self.redis_master.get(redis_key)
            current_data = json.loads(current_data_raw) if current_data_raw else {}
            current_data.update(result)
            current_data['updated_at'] = datetime.utcnow().isoformat()
            self.redis_master.set(redis_key, json.dumps(current_data), ex=86400)
            logger.info(f"✅ Job {job_id} actualizado en Redis a estado: {result['status']}")
        except Exception as e:
            # Loguear el error pero NO matar el worker
            logger.error(f"⚠️ Error no crítico actualizando Redis para {job_id}: {e}")

    def on_message(self, channel, method, properties, body):
        try:
            message = json.loads(body)
            job_id = message.get('job_id')
            
            # Notificar inicio
            self.update_job_status(job_id, {'status': 'processing', 'worker_id': os.getpid()})

            # Procesar
            result = self.process_pdf(message)
            
            # Notificar fin
            self.update_job_status(job_id, result)
            
            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"❌ Error fatal en on_message: {e}")
            traceback.print_exc()
            if 'job_id' in locals():
                 self.update_job_status(job_id, {'status': 'failed', 'error': str(e)})
            # NACK para no perder el mensaje si es un error transitorio
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start_consuming(self):
        if not self.channel: return
        self.channel.exchange_declare(exchange='tutor.processing', exchange_type='topic', durable=True)
        for q in self.queues:
            self.channel.queue_declare(queue=q, durable=True, arguments={'x-max-priority': 10})
            self.channel.queue_bind(exchange='tutor.processing', queue=q, routing_key=q)
            self.channel.basic_consume(queue=q, on_message_callback=self.on_message)
            
        logger.info("🚀 Worker iniciado y esperando mensajes...")
        self.channel.start_consuming()

def main():
    worker = PDFWorkerMultiQueue()
    # Reintentos de conexión
    for i in range(5):
        if worker.connect():
            worker.start_consuming()
            break
        time.sleep(5)

if __name__ == "__main__":
    main()