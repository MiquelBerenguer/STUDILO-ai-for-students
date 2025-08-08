#!/usr/bin/env python3
"""
Queue Producer
Envía trabajos a las colas de RabbitMQ
"""

import pika
import json
import uuid
import logging
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
        self.rabbitmq_url = rabbitmq_url or 'amqp://REDACTED:REDACTED@localhost:5672/tutor_ia'
        self.connection = None
        self.channel = None
    
    def connect(self):
        """Establece conexión con RabbitMQ"""
        try:
            parameters = pika.URLParameters(self.rabbitmq_url)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            return True
        except Exception as e:
            logger.error(f"Error conectando a RabbitMQ: {e}")
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
        if not self.channel:
            self.connect()
        
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
            self.channel.basic_publish(
                exchange='tutor.processing',
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
            raise
    
    def send_notification(
        self,
        user_id: str,
        notification_type: str,
        content: Dict[str, Any]
    ):
        """
        Envía una notificación a la cola
        
        Args:
            user_id: ID del usuario
            notification_type: Tipo de notificación (email, push, etc.)
            content: Contenido de la notificación
        """
        if not self.channel:
            self.connect()
        
        message = {
            'notification_id': str(uuid.uuid4()),
            'user_id': user_id,
            'type': notification_type,
            'content': content,
            'created_at': datetime.utcnow().isoformat()
        }
        
        try:
            self.channel.basic_publish(
                exchange='tutor.direct',
                routing_key='notify',
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            
            logger.info(f"📧 Notificación enviada: {message['notification_id']}")
            
        except Exception as e:
            logger.error(f"❌ Error enviando notificación: {e}")
            raise
    
    def close(self):
        """Cierra la conexión"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()

# Ejemplo de uso
if __name__ == "__main__":
    producer = QueueProducer()
    
    # Enviar un trabajo de procesamiento
    job_id = producer.send_pdf_processing_job(
        filename="documento_ejemplo.pdf",
        file_path="pdfs/user123/documento_ejemplo.pdf",
        user_id="user123",
        priority=False,
        require_analysis=True,
        metadata={
            'pages': 10,
            'size_mb': 2.5
        }
    )
    
    print(f"Job creado: {job_id}")
    
    # Enviar una notificación
    producer.send_notification(
        user_id="user123",
        notification_type="email",
        content={
            'subject': 'PDF Procesado',
            'body': f'Tu documento ha sido procesado exitosamente. Job ID: {job_id}'
        }
    )
    
    producer.close()