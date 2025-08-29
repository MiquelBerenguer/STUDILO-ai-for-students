#!/usr/bin/env python3
"""
Queue Producer - SIMPLIFIED VERSION
Envía trabajos a las colas de RabbitMQ sin declarar exchange en connect
"""
import pika
import json
import uuid
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class QueueProducer:
    def __init__(self, rabbitmq_url: str = None):
        """
        Inicializa el productor de mensajes
        
        Args:
            rabbitmq_url: URL de conexión a RabbitMQ
        """
        # Usar variable de entorno o valor por defecto correcto
        self.rabbitmq_url = rabbitmq_url or os.getenv(
            'RABBITMQ_URL', 
            'amqp://REDACTED:REDACTED@rabbitmq:5672/tutor_ia'
        )
        self.connection = None
        self.channel = None
        logger.info(f"Configurando QueueProducer con URL: {self.rabbitmq_url}")
        
    def connect(self):
        """Establece conexión con RabbitMQ - VERSIÓN SIMPLIFICADA"""
        try:
            logger.info("Intentando conectar a RabbitMQ...")
            parameters = pika.URLParameters(self.rabbitmq_url)
            # Añadir timeout para evitar bloqueos
            parameters.connection_attempts = 3
            parameters.retry_delay = 2
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # NO declarar exchange aquí - solo establecer conexión
            logger.info("✅ Conectado exitosamente a RabbitMQ")
            return True
            
        except Exception as e:
            logger.error(f"Error conectando a RabbitMQ: {e}")
            return False
    
    def ensure_exchange_and_queue(self):
        """Asegura que el exchange y la cola existan - llamar solo cuando sea necesario"""
        if not self.channel:
            return False
            
        try:
            # Declarar el exchange si no existe
            self.channel.exchange_declare(
                exchange='tutor.processing',
                exchange_type='topic',
                durable=True,
                passive=False  # No fallar si no existe, crearlo
            )
            
            # Declarar la cola
            self.channel.queue_declare(
                queue='pdf_processing',
                durable=True,
                arguments={
                    'x-max-priority': 10
                }
            )
            
            # Bind de la cola al exchange
            self.channel.queue_bind(
                exchange='tutor.processing',
                queue='pdf_processing',
                routing_key='pdf.process'
            )
            
            self.channel.queue_bind(
                exchange='tutor.processing',
                queue='pdf_processing',
                routing_key='pdf.process.priority'
            )
            
            logger.info("Exchange y cola configurados correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error configurando exchange/cola: {e}")
            return False
    
    def send_pdf_processing_job(
        self,
        filename: str,
        file_path: str,
        user_id: str,
        priority: bool = False,
        require_analysis: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Envía un trabajo de procesamiento de PDF a la cola
        
        Args:
            filename: Nombre del archivo
            file_path: Ruta en MinIO/S3
            user_id: ID del usuario
            priority: Si es prioritario
            require_analysis: Si requiere análisis de IA posterior
            metadata: Metadata adicional
            
        Returns:
            job_id del trabajo creado
        """
        if not self.channel or not self.connection or self.connection.is_closed:
            if not self.connect():
                raise Exception("No se pudo conectar a RabbitMQ")
            # Asegurar que el exchange y cola existan antes de enviar
            self.ensure_exchange_and_queue()
        
        job_id = str(uuid.uuid4())
        
        message = {
            'job_id': job_id,
            'filename': filename,
            'file_path': file_path,
            'user_id': user_id,
            'require_analysis': require_analysis,
            'created_at': datetime.utcnow().isoformat(),
            'metadata': metadata or {}
        }
        
        # Determinar routing key según prioridad
        routing_key = 'pdf.process.priority' if priority else 'pdf.process'
        
        try:
            # Si usamos el exchange default (vacío), no necesitamos routing key especial
            # Pero si usamos un exchange custom, sí
            self.channel.basic_publish(
                exchange='tutor.processing',  # Usar el exchange custom
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Mensaje persistente
                    content_type='application/json',
                    priority=10 if priority else 5
                )
            )
            
            logger.info(f"✅ Job enviado: {job_id} - {filename}")
            return job_id
            
        except Exception as e:
            logger.error(f"❌ Error enviando job: {e}")
            # Intentar reconectar para el próximo mensaje
            self.connection = None
            self.channel = None
            raise
    
    def close(self):
        """Cierra la conexión con RabbitMQ"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("Conexión a RabbitMQ cerrada")