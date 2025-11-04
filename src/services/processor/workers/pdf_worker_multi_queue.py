#!/usr/bin/env python3
"""
PDF Processing Worker - Multi-Queue Version with MinIO and Real OCR
Versión completa con OCR usando Tesseract
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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MinIOHelper:
    """Helper class para operaciones con MinIO"""
    
    def __init__(self):
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
        """
        Sube archivo a MinIO sin metadata
        Nota: Los metadata con guiones causan errores de firma en MinIO
        """
        if not self.client:
            return False
        
        try:
            data_stream = io.BytesIO(data)
            
            # Subir SIN metadata para evitar errores de firma
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
            logger.error(f"   Detalles: bucket={bucket}, object={object_name}, size={len(data)}")
            return False

class PDFWorkerMultiQueue:
    def __init__(self, rabbitmq_url: str = None):
        """
        Inicializa el worker de procesamiento de PDFs
        
        Args:
            rabbitmq_url: URL de conexión a RabbitMQ
        """
        self.rabbitmq_url = rabbitmq_url or os.getenv(
            'RABBITMQ_URL',
            'amqp://REDACTED:REDACTED@rabbitmq:5672/tutor_ia'
        )
        self.connection = None
        self.channel = None
        self.consumer_tags = {}
        
        # Inicializar MinIO helper
        self.minio = MinIOHelper()
        
        # Definir las colas a escuchar (orden = prioridad)
        self.queues = [
            'pdf.process.priority',  # Primera prioridad
            'pdf.process'            # Segunda prioridad
        ]
        
        # Verificar disponibilidad de OCR
        if OCR_AVAILABLE:
            logger.info("✅ OCR disponible con Tesseract")
        else:
            logger.warning("⚠️ OCR no disponible - se extraerá solo texto embebido")
        
    def connect(self):
        """Establece conexión con RabbitMQ"""
        try:
            parameters = pika.URLParameters(self.rabbitmq_url)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Configurar QoS - procesar 1 mensaje a la vez
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info("✅ Conectado a RabbitMQ")
            return True
        except Exception as e:
            logger.error(f"❌ Error conectando a RabbitMQ: {e}")
            return False
    
    def extract_text_from_pdf(self, pdf_content: bytes, filename: str) -> tuple[str, int, bool]:
        """
        Extrae texto de un PDF usando PyPDF2 y OCR si es necesario
        
        Returns:
            tuple: (texto_extraido, num_paginas, se_uso_ocr)
        """
        text_extracted = ""
        pages_count = 0
        ocr_used = False
        
        if not OCR_AVAILABLE:
            return "OCR no disponible", 0, False
        
        try:
            # Crear archivo temporal
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_file.flush()
                tmp_path = tmp_file.name
            
            try:
                # Paso 1: Intentar extraer texto embebido con PyPDF2
                logger.info(f"📖 Intentando extraer texto embebido de {filename}...")
                
                with open(tmp_path, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    pages_count = len(pdf_reader.pages)
                    logger.info(f"📄 PDF tiene {pages_count} páginas")
                    
                    # Extraer texto de cada página
                    for page_num, page in enumerate(pdf_reader.pages):
                        try:
                            page_text = page.extract_text()
                            if page_text and len(page_text.strip()) > 10:
                                text_extracted += f"\n\n=== PÁGINA {page_num + 1} ===\n"
                                text_extracted += page_text
                        except Exception as e:
                            logger.warning(f"Error extrayendo texto de página {page_num}: {e}")
                
                # Verificar si se extrajo suficiente texto
                text_length = len(text_extracted.strip())
                logger.info(f"📏 Texto extraído: {text_length} caracteres")
                
                # Paso 2: Si no hay suficiente texto, usar OCR
                if text_length < 100 and pages_count > 0:
                    logger.info("🔍 Texto insuficiente, aplicando OCR con Tesseract...")
                    ocr_used = True
                    
                    try:
                        # Convertir PDF a imágenes
                        images = convert_from_bytes(
                            pdf_content,
                            dpi=200,
                            first_page=1,
                            last_page=min(10, pages_count)  # Limitar a 10 páginas para no tardar mucho
                        )
                        
                        text_extracted = ""
                        for i, image in enumerate(images):
                            logger.info(f"🔍 Aplicando OCR a página {i+1}/{len(images)}...")
                            
                            # Aplicar OCR
                            page_text = pytesseract.image_to_string(
                                image,
                                lang='spa+eng'  # Español e inglés
                            )
                            
                            if page_text:
                                text_extracted += f"\n\n=== PÁGINA {i+1} (OCR) ===\n"
                                text_extracted += page_text
                            
                            # Mostrar progreso
                            if (i + 1) % 5 == 0:
                                logger.info(f"   Procesadas {i+1}/{len(images)} páginas...")
                        
                        logger.info(f"✅ OCR completado: {len(text_extracted)} caracteres extraídos")
                        
                    except Exception as e:
                        logger.error(f"❌ Error durante OCR: {e}")
                        text_extracted = f"Error aplicando OCR: {str(e)}"
                
                # Si todavía no hay texto
                if len(text_extracted.strip()) < 10:
                    text_extracted = f"No se pudo extraer texto del PDF '{filename}'. El archivo puede estar vacío o contener solo imágenes."
                    
            finally:
                # Limpiar archivo temporal
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            logger.error(f"❌ Error procesando PDF: {e}")
            text_extracted = f"Error procesando PDF: {str(e)}"
        
        return text_extracted, pages_count, ocr_used
    
    def process_pdf(self, pdf_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa un archivo PDF con OCR real
        
        Args:
            pdf_data: Datos del PDF a procesar
            
        Returns:
            Resultado del procesamiento
        """
        job_id = pdf_data.get('job_id', 'unknown')
        filename = pdf_data.get('filename', 'unknown.pdf')
        minio_object_key = pdf_data.get('minio_object_key')
        minio_bucket = pdf_data.get('minio_bucket', 'uploads')
        
        logger.info(f"📄 Procesando PDF: {filename} (Job: {job_id})")
        
        pdf_content = None
        text_extracted = ""
        pages_count = 0
        ocr_used = False
        processing_time = 0
        start_time = time.time()
        
        # Intentar descargar de MinIO si está disponible
        if minio_object_key and self.minio.client:
            logger.info(f"🔍 Descargando de MinIO: {minio_bucket}/{minio_object_key}")
            pdf_content = self.minio.download_file(minio_bucket, minio_object_key)
            
            if pdf_content:
                logger.info(f"✅ Archivo descargado: {len(pdf_content)} bytes")
                
                # Procesar PDF con OCR real
                text_extracted, pages_count, ocr_used = self.extract_text_from_pdf(pdf_content, filename)
                
            else:
                logger.warning("⚠️ No se pudo descargar de MinIO")
                text_extracted = "Error: No se pudo descargar el archivo de MinIO"
        
        # Si no se pudo procesar desde MinIO
        if not pdf_content:
            logger.warning("📝 No se pudo obtener el archivo desde MinIO")
            text_extracted = f"Error: No se pudo obtener el archivo {filename} desde MinIO"
            pages_count = 0
        
        processing_time = time.time() - start_time
        
        # Preparar resultado
        result = {
            'status': 'completed',
            'job_id': job_id,
            'filename': filename,
            'pages': pages_count,
            'text_extracted': text_extracted[:10000],  # Limitar a 10000 caracteres
            'text_length': len(text_extracted),
            'processing_time': processing_time,
            'worker_id': os.getpid(),
            'queue': pdf_data.get('_queue_name', 'unknown'),
            'minio_available': self.minio.client is not None,
            'processed_from_minio': pdf_content is not None,
            'ocr_used': ocr_used,
            'processed_at': datetime.utcnow().isoformat()
        }
        
        # Intentar guardar resultado en MinIO
        if self.minio.client and pdf_content:
            try:
                # Guardar resultado como JSON
                result_json = json.dumps(result, indent=2, ensure_ascii=False)
                result_key = f"{job_id}/result.json"
                
                success_json = self.minio.upload_file(
                    'processed',
                    result_key,
                    result_json.encode('utf-8')
                )
                
                if success_json:
                    logger.info(f"✅ Resultado JSON guardado en MinIO: processed/{result_key}")
                
                # Guardar texto extraído completo
                if text_extracted and len(text_extracted) > 10:
                    text_key = f"{job_id}/extracted_text.txt"
                    success_text = self.minio.upload_file(
                        'processed',
                        text_key,
                        text_extracted.encode('utf-8')
                    )
                    
                    if success_text:
                        logger.info(f"✅ Texto extraído guardado en MinIO: processed/{text_key}")
                
                if success_json:
                    logger.info(f"✅ Todos los resultados guardados en MinIO: processed/{job_id}/")
                
            except Exception as e:
                logger.error(f"⚠️ Error guardando en MinIO: {e}")
                logger.error(traceback.format_exc())
        
        logger.info(f"✅ PDF procesado en {processing_time:.2f}s")
        logger.info(f"   Páginas: {pages_count}")
        logger.info(f"   OCR usado: {'Sí' if ocr_used else 'No'}")
        logger.info(f"   Caracteres extraídos: {len(text_extracted)}")
        
        return result
    
    def on_message(self, channel, method, properties, body):
        """
        Callback para procesar mensajes de la cola
        
        Args:
            channel: Canal de RabbitMQ
            method: Método de entrega
            properties: Propiedades del mensaje
            body: Cuerpo del mensaje
        """
        try:
            # Decodificar mensaje
            message = json.loads(body)
            message['_queue_name'] = method.routing_key  # Guardar de qué cola vino
            
            logger.info(f"📨 Mensaje recibido de cola '{method.routing_key}': {message.get('job_id', 'unknown')}")
            
            # Procesar PDF
            result = self.process_pdf(message)
            
            # Actualizar estado en base de datos
            self.update_job_status(message.get('job_id'), result)
            
            # Confirmar mensaje procesado
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"✅ Mensaje confirmado: {method.delivery_tag}")
            
            # Si necesita análisis de IA, enviar a siguiente cola
            if message.get('require_analysis', False):
                self.send_to_analysis_queue(message, result)
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error decodificando mensaje: {e}")
            # Rechazar mensaje y enviarlo a DLQ
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje: {e}")
            logger.error(traceback.format_exc())
            
            # Decidir si reintentar o enviar a DLQ
            retry_count = properties.headers.get('x-retry-count', 0) if properties.headers else 0
            
            if retry_count < 3:
                # Reintentar con delay
                self.retry_message(channel, method, properties, body, retry_count)
            else:
                # Enviar a Dead Letter Queue
                logger.error(f"🚫 Mensaje enviado a DLQ después de {retry_count} reintentos")
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    def retry_message(self, channel, method, properties, body, retry_count):
        """Reintenta procesar un mensaje con delay exponencial"""
        retry_count += 1
        delay = min(300, 10 * (2 ** retry_count))  # Max 5 minutos
        
        logger.warning(f"🔄 Reintentando mensaje (intento {retry_count}) con delay de {delay}s")
        
        # Crear headers con contador de reintentos
        headers = properties.headers or {}
        headers['x-retry-count'] = retry_count
        
        # Publicar mensaje con delay
        channel.basic_publish(
            exchange='tutor.processing',
            routing_key='pdf.process.retry',
            body=body,
            properties=pika.BasicProperties(
                headers=headers,
                expiration=str(delay * 1000)  # TTL en milisegundos
            )
        )
        
        # Confirmar mensaje original
        channel.basic_ack(delivery_tag=method.delivery_tag)
    
    def update_job_status(self, job_id: str, result: Dict[str, Any]):
        """Actualizar el estado del trabajo en la base de datos"""
        try:
            # Por ahora solo logging, ya que la API está en otro servicio
            logger.info(f"📊 Job {job_id} actualizado: {result['status']}")
            logger.info(f"   MinIO: {'Sí' if result.get('processed_from_minio') else 'No'}")
            logger.info(f"   OCR: {'Sí' if result.get('ocr_used') else 'No'}")
            logger.info(f"   Tiempo: {result.get('processing_time', 0):.2f}s")
            
            # TODO: Implementar actualización real:
            # - Usar Redis para actualizar estado
            # - O hacer llamada HTTP a la API
            # - O actualizar directamente en PostgreSQL
            
        except Exception as e:
            logger.error(f"❌ Error actualizando estado: {e}")
    
    def send_to_analysis_queue(self, original_message: Dict, processing_result: Dict):
        """Envía el resultado a la cola de análisis de IA"""
        try:
            # Primero crear el exchange si no existe
            self.channel.exchange_declare(
                exchange='tutor.processing',
                exchange_type='topic',
                durable=True
            )
            
            analysis_message = {
                'job_id': original_message.get('job_id'),
                'text': processing_result.get('text_extracted'),
                'metadata': {
                    'filename': original_message.get('filename'),
                    'pages': processing_result.get('pages', 0),
                    'processing_time': processing_result.get('processing_time'),
                    'processed_from_minio': processing_result.get('processed_from_minio', False),
                    'ocr_used': processing_result.get('ocr_used', False)
                }
            }
            
            self.channel.basic_publish(
                exchange='tutor.processing',
                routing_key='ai.analysis',
                body=json.dumps(analysis_message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Mensaje persistente
                    content_type='application/json'
                )
            )
            logger.info(f"📤 Enviado a cola de análisis: {original_message.get('job_id')}")
        except Exception as e:
            logger.error(f"❌ Error enviando a cola de análisis: {e}")
    
    def start_consuming(self):
        """Inicia el consumo de mensajes de múltiples colas"""
        if not self.channel:
            logger.error("❌ No hay conexión establecida")
            return
        
        try:
            # Primero asegurar que el exchange existe
            self.channel.exchange_declare(
                exchange='tutor.processing',
                exchange_type='topic',
                durable=True
            )
            
            # Configurar consumers para cada cola
            for queue_name in self.queues:
                try:
                    # Declarar la cola si no existe
                    self.channel.queue_declare(
                        queue=queue_name,
                        durable=True,
                        arguments={
                            'x-max-priority': 10
                        }
                    )
                    
                    # Bind al exchange
                    self.channel.queue_bind(
                        exchange='tutor.processing',
                        queue=queue_name,
                        routing_key=queue_name
                    )
                    
                    # Crear consumer
                    consumer_tag = self.channel.basic_consume(
                        queue=queue_name,
                        on_message_callback=self.on_message,
                        auto_ack=False  # ACK manual para confirmar procesamiento
                    )
                    
                    self.consumer_tags[queue_name] = consumer_tag
                    logger.info(f"🎯 Escuchando cola: {queue_name}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error configurando cola {queue_name}: {e}")
            
            if not self.consumer_tags:
                logger.error("❌ No se pudo conectar a ninguna cola")
                return
            
            logger.info(f"👷 Worker iniciado escuchando {len(self.consumer_tags)} colas")
            logger.info(f"📦 MinIO: {'Conectado' if self.minio.client else 'No disponible'}")
            logger.info(f"🔍 OCR: {'Disponible' if OCR_AVAILABLE else 'No disponible'}")
            logger.info("👉 Procesando primero mensajes prioritarios")
            logger.info("🛑 Presiona CTRL+C para detener...")
            
            # Iniciar consumo
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("🛑 Deteniendo worker...")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"❌ Error en el worker: {e}")
            self.stop_consuming()
    
    def stop_consuming(self):
        """Detiene el consumo de mensajes de forma limpia"""
        if self.channel:
            try:
                # Cancelar todos los consumers
                for queue_name, consumer_tag in self.consumer_tags.items():
                    self.channel.basic_cancel(consumer_tag)
                    logger.info(f"✅ Dejó de escuchar: {queue_name}")
                
                self.channel.stop_consuming()
                logger.info("✅ Consumo detenido")
            except Exception as e:
                logger.error(f"Error deteniendo consumo: {e}")
        
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("🔌 Conexión cerrada")

def main():
    """Función principal del worker"""
    logger.info("=" * 60)
    logger.info("🚀 PDF Processing Worker v3.0 - Con MinIO y OCR Real")
    logger.info("=" * 60)
    
    worker = PDFWorkerMultiQueue()
    
    # Reintentar conexión si falla
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        if worker.connect():
            worker.start_consuming()
            break
        else:
            if attempt < max_retries - 1:
                logger.warning(f"⏳ Reintentando conexión en {retry_delay}s... (intento {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # Backoff exponencial
            else:
                logger.error("❌ No se pudo conectar después de múltiples intentos")
                sys.exit(1)

if __name__ == "__main__":
    main()