import aio_pika
from aio_pika import Message, DeliveryMode
from typing import Optional, Dict, Any, Callable
import json
import structlog
import asyncio
from ..config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class RabbitMQClient:
    def __init__(self):
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.exchange: Optional[aio_pika.Exchange] = None
        
        # Configuración de colas
        self.exchange_name = "document_processing"
        self.queue_name = "document_queue"
        self.routing_key = "process.document"
        
    async def connect(self):
        """Inicializar conexión a RabbitMQ"""
        try:
            # Crear conexión robusta (con reconexión automática)
            self.connection = await aio_pika.connect_robust(
                settings.rabbitmq_url,
                connection_attempts=3,
                retry_delay=5.0
            )
            
            # Crear canal
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=10)
            
            # Declarar exchange
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                aio_pika.ExchangeType.DIRECT,
                durable=True
            )
            
            # Declarar cola
            queue = await self.channel.declare_queue(
                self.queue_name,
                durable=True,
                arguments={
                    "x-message-ttl": 86400000,  # 24 horas
                    "x-max-length": 10000,       # Máximo 10k mensajes
                    "x-overflow": "reject-publish"  # Rechazar nuevos si está llena
                }
            )
            
            # Bind de cola a exchange
            await queue.bind(self.exchange, routing_key=self.routing_key)
            
            logger.info("RabbitMQ connection successful")
            
        except Exception as e:
            logger.error("RabbitMQ connection failed", error=str(e))
            raise
    
    async def disconnect(self):
        """Cerrar conexión a RabbitMQ"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            
    async def publish_task(self, task_data: Dict[str, Any]) -> bool:
        """Publicar tarea de procesamiento"""
        try:
            message = Message(
                body=json.dumps(task_data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
                headers={
                    "task_type": task_data.get("type", "process_document")
                }
            )
            
            await self.exchange.publish(
                message,
                routing_key=self.routing_key
            )
            
            logger.info("Task published successfully", 
                       job_id=task_data.get("job_id"))
            return True
            
        except Exception as e:
            logger.error("Failed to publish task", error=str(e))
            return False
    
    async def consume_tasks(self, callback: Callable) -> None:
        """Consumir tareas de la cola"""
        try:
            queue = await self.channel.declare_queue(
                self.queue_name,
                durable=True
            )
            
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            # Decodificar mensaje
                            data = json.loads(message.body.decode())
                            
                            # Procesar con callback
                            await callback(data)
                            
                            logger.info("Task processed successfully",
                                      job_id=data.get("job_id"))
                                      
                        except Exception as e:
                            logger.error("Task processing failed", 
                                       error=str(e),
                                       will_retry=message.redelivered)
                            
                            # Re-queue si es el primer intento
                            if not message.redelivered:
                                await message.reject(requeue=True)
                            else:
                                # Enviar a dead letter queue después de reintentos
                                await self.send_to_dlq(message.body)
                                
        except Exception as e:
            logger.error("Consumer error", error=str(e))
            raise
    
    async def send_to_dlq(self, message_body: bytes):
        """Enviar mensaje a Dead Letter Queue"""
        try:
            dlq = await self.channel.declare_queue(
                "document_queue_dlq",
                durable=True
            )
            
            await self.channel.default_exchange.publish(
                Message(
                    body=message_body,
                    delivery_mode=DeliveryMode.PERSISTENT
                ),
                routing_key=dlq.name
            )
            
            logger.warning("Message sent to DLQ")
            
        except Exception as e:
            logger.error("Failed to send to DLQ", error=str(e))
    
    async def get_queue_size(self) -> int:
        """Obtener número de mensajes en cola"""
        try:
            queue = await self.channel.declare_queue(
                self.queue_name,
                durable=True,
                passive=True  # No crear si no existe
            )
            return queue.declaration_result.message_count
        except Exception:
            return 0

# Instancia global
rabbitmq_client = RabbitMQClient()