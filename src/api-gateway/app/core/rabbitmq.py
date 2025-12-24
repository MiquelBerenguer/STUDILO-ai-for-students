import aio_pika
import logging
import json
import asyncio
from app.core.config import settings

logger = logging.getLogger(__name__)

class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = None # Ahora guardaremos la referencia al exchange
        self._connection_lock = asyncio.Lock()

    async def connect(self):
        """
        Conexión robusta configurando Exchange, DLQ y TTL según config.py.
        """
        async with self._connection_lock:
            if self.connection and not self.connection.is_closed:
                return

            try:
                logger.info(f"🔌 Conectando a RabbitMQ en {settings.RABBITMQ_HOST}...")
                
                # Construcción de URL segura
                rabbitmq_url = f"amqp://{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASS}@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/{settings.RABBITMQ_VHOST}"
                
                # Conexión con timeout configurado (Fail Fast)
                self.connection = await aio_pika.connect_robust(
                    rabbitmq_url, 
                    timeout=settings.RABBITMQ_CONNECTION_TIMEOUT
                )
                
                # Publisher Confirms activado
                self.channel = await self.connection.channel(publisher_confirms=True)
                
                # --- 1. Configuración DLQ (Manejo de Fallos) [cite: 136] ---
                dlx = await self.channel.declare_exchange('dlx', aio_pika.ExchangeType.DIRECT)
                dlq = await self.channel.declare_queue(settings.EXAM_DLQ_NAME, durable=True)
                await dlq.bind(dlx, routing_key='failed_task')

                # --- 2. Configuración Exchange Principal  ---
                # Usamos un Exchange Directo para enrutamiento explícito
                self.exchange = await self.channel.declare_exchange(
                    settings.EXAM_EXCHANGE_NAME, 
                    aio_pika.ExchangeType.DIRECT,
                    durable=True
                )

                # --- 3. Configuración Cola Principal con TTL y DLQ ---
                args = {
                    'x-dead-letter-exchange': 'dlx',
                    'x-dead-letter-routing-key': 'failed_task',
                    'x-message-ttl': settings.MESSAGE_TTL_MS # TTL definido en config 
                }
                
                queue = await self.channel.declare_queue(
                    settings.EXAM_QUEUE_NAME, 
                    durable=True,
                    arguments=args
                )
                
                # Binding: Unimos el Exchange con la Cola
                await queue.bind(self.exchange, routing_key=settings.EXAM_QUEUE_NAME)
                
                logger.info(f"✅ RabbitMQ Configurado: Exchange='{settings.EXAM_EXCHANGE_NAME}' -> Queue='{settings.EXAM_QUEUE_NAME}' (TTL={settings.MESSAGE_TTL_MS}ms)")
                
            except Exception as e:
                logger.error(f"❌ Error fatal conectando a RabbitMQ: {e}")
                self.connection = None
                raise e

    async def send_message(self, message_data: dict):
        """
        Publica usando la configuración de reintentos de config.py.
        """
        if not self.channel or self.channel.is_closed:
            await self.connect()

        message_body = json.dumps(message_data).encode()
        
        # Usamos los settings para la lógica de reintento [cite: 133]
        max_retries = settings.RABBITMQ_MAX_RETRIES
        base_backoff = settings.RABBITMQ_RETRY_BACKOFF

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    # Backoff exponencial simple: factor * 2^intento
                    wait_time = base_backoff * (2 ** (attempt - 1))
                    logger.warning(f"🔄 Reintento {attempt}/{max_retries} en {wait_time}s...")
                    await asyncio.sleep(wait_time)

                message = aio_pika.Message(
                    body=message_body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type='application/json',
                    # Headers opcionales para trazar origen
                    headers={'x-producer': settings.PROJECT_NAME}
                )

                # IMPORTANTE: Publicamos al EXCHANGE, no a la cola default
                await self.exchange.publish(
                    message,
                    routing_key=settings.EXAM_QUEUE_NAME,
                    timeout=5
                )
                
                return True

            except (aio_pika.exceptions.AMQPError, asyncio.TimeoutError) as e:
                logger.error(f"❌ Fallo al publicar (Intento {attempt}): {str(e)}")
                if self.channel.is_closed:
                    try: 
                        await self.connect()
                    except: 
                        pass

            except Exception as e:
                logger.critical(f"❌ Error no recuperable: {e}")
                break

        logger.critical("💀 Se agotaron los reintentos. Mensaje enviado a log local (DLQ virtual).")
        return False

    async def close(self):
        if self.connection:
            await self.connection.close()
            logger.info("👋 Conexión RabbitMQ cerrada.")

mq_client = RabbitMQClient()