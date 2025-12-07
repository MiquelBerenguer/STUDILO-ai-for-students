import pika
import json
import os

# Configuración básica (lee del .env o usa defaults)
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "user")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASSWORD", "password")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))

class RabbitMQProducer:
    """
    Cliente para PUBLICAR mensajes en RabbitMQ.
    """
    def __init__(self):
        self.credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        self.parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=self.credentials,
            virtual_host='/'
        )

    def publish(self, queue_name: str, message: dict):
        connection = None
        try:
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            
            # Aseguramos que la cola exista (Idempotencia)
            channel.queue_declare(queue=queue_name, durable=True)
            
            # Publicamos
            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistente
                )
            )
            print(f"✅ [RabbitMQ] Mensaje enviado a '{queue_name}'")
            
        except Exception as e:
            print(f"❌ [RabbitMQ Error] No se pudo enviar mensaje: {str(e)}")
            raise e
        finally:
            if connection:
                connection.close()