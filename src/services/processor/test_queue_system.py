#!/usr/bin/env python3
"""
Test Queue System
Script para probar el sistema completo de colas
"""

import sys
import os
import time
import threading
import logging

# Añadir el path del proyecto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from producers.queue_producer import QueueProducer
from workers.pdf_worker import PDFWorker

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_worker_in_thread():
    """Ejecuta el worker en un thread separado"""
    logger.info("🚀 Iniciando worker en thread separado...")
    worker = PDFWorker()
    if worker.connect():
        # Configurar para que termine después de procesar 1 mensaje
        def process_one_message(ch, method, properties, body):
            worker.on_message(ch, method, properties, body)
            ch.stop_consuming()
        
        worker.channel.basic_consume(
            queue='pdf.process',
            on_message_callback=process_one_message,
            auto_ack=False
        )
        
        try:
            worker.channel.start_consuming()
        except Exception as e:
            logger.error(f"Error en worker: {e}")
        finally:
            worker.stop_consuming()

def test_basic_flow():
    """Prueba el flujo básico: enviar mensaje y procesarlo"""
    print("\n" + "="*50)
    print("🧪 TEST 1: Flujo básico de procesamiento")
    print("="*50)
    
    # Iniciar worker en thread
    worker_thread = threading.Thread(target=run_worker_in_thread)
    worker_thread.start()
    
    # Esperar a que el worker esté listo
    time.sleep(2)
    
    # Crear producer y enviar mensaje
    producer = QueueProducer()
    if producer.connect():
        job_id = producer.send_pdf_processing_job(
            filename="test_document.pdf",
            file_path="test/path/test_document.pdf",
            user_id="test_user_123",
            priority=False,
            require_analysis=True,
            metadata={
                'pages': 5,
                'size_mb': 1.2,
                'test': True
            }
        )
        
        print(f"\n✅ Mensaje enviado con job_id: {job_id}")
        producer.close()
    
    # Esperar a que el worker procese
    worker_thread.join(timeout=10)
    
    if worker_thread.is_alive():
        print("⚠️  Worker aún procesando...")
    else:
        print("✅ Worker terminó de procesar")
    
    print("\n" + "-"*50 + "\n")

def test_priority_queue():
    """Prueba el envío a cola prioritaria"""
    print("\n" + "="*50)
    print("🧪 TEST 2: Cola prioritaria")
    print("="*50)
    
    producer = QueueProducer()
    if producer.connect():
        # Enviar mensaje prioritario
        job_id = producer.send_pdf_processing_job(
            filename="urgent_document.pdf",
            file_path="test/path/urgent_document.pdf", 
            user_id="vip_user",
            priority=True,  # 👈 Prioritario
            metadata={'pages': 2, 'urgent': True}
        )
        
        print(f"✅ Mensaje prioritario enviado: {job_id}")
        producer.close()
    
    print("\n" + "-"*50 + "\n")

def test_notifications():
    """Prueba el envío de notificaciones"""
    print("\n" + "="*50)
    print("🧪 TEST 3: Sistema de notificaciones")
    print("="*50)
    
    producer = QueueProducer()
    if producer.connect():
        # Enviar notificación
        producer.send_notification(
            user_id="test_user_123",
            notification_type="email",
            content={
                'subject': 'Prueba de notificación',
                'body': 'Este es un mensaje de prueba del sistema de colas',
                'template': 'test_notification'
            }
        )
        
        print("✅ Notificación enviada")
        producer.close()
    
    print("\n" + "-"*50 + "\n")

def check_queue_status():
    """Verifica el estado de las colas"""
    print("\n" + "="*50)
    print("📊 Estado de las colas")
    print("="*50)
    
    try:
        import requests
        from requests.auth import HTTPBasicAuth
        
        # Credenciales de RabbitMQ
        auth = HTTPBasicAuth('REDACTED', 'REDACTED')
        base_url = 'http://localhost:15672/api'
        
        # Obtener información de las colas
        response = requests.get(f'{base_url}/queues/tutor_ia', auth=auth)
        
        if response.status_code == 200:
            queues = response.json()
            
            print(f"\n📬 Colas encontradas: {len(queues)}")
            print("-" * 40)
            
            for queue in queues:
                name = queue['name']
                messages = queue.get('messages', 0)
                messages_ready = queue.get('messages_ready', 0)
                messages_unacked = queue.get('messages_unacknowledged', 0)
                
                print(f"\n📌 Cola: {name}")
                print(f"   Total mensajes: {messages}")
                print(f"   Listos: {messages_ready}")
                print(f"   Sin confirmar: {messages_unacked}")
        else:
            print("❌ No se pudo conectar a la API de RabbitMQ")
            
    except Exception as e:
        print(f"⚠️  Error verificando colas: {e}")
        print("💡 Asegúrate de tener 'requests' instalado: pip install requests")
    
    print("\n" + "-"*50 + "\n")

def main():
    """Función principal de pruebas"""
    print("\n🔧 SISTEMA DE PRUEBAS - COLAS RABBITMQ")
    print("="*50)
    
    # Verificar conexión a RabbitMQ
    producer = QueueProducer()
    if not producer.connect():
        print("❌ No se puede conectar a RabbitMQ")
        print("💡 Asegúrate de que RabbitMQ está corriendo")
        return
    
    producer.close()
    print("✅ Conexión a RabbitMQ exitosa")
    
    while True:
        print("\n📋 Selecciona una prueba:")
        print("1. Flujo básico (enviar y procesar mensaje)")
        print("2. Cola prioritaria")
        print("3. Sistema de notificaciones")
        print("4. Ver estado de las colas")
        print("5. Ejecutar todas las pruebas")
        print("0. Salir")
        
        choice = input("\nOpción: ").strip()
        
        if choice == '1':
            test_basic_flow()
        elif choice == '2':
            test_priority_queue()
        elif choice == '3':
            test_notifications()
        elif choice == '4':
            check_queue_status()
        elif choice == '5':
            test_basic_flow()
            test_priority_queue()
            test_notifications()
            check_queue_status()
        elif choice == '0':
            print("\n👋 ¡Hasta luego!")
            break
        else:
            print("❌ Opción no válida")

if __name__ == "__main__":
    main()