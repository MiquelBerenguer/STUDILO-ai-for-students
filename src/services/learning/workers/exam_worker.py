#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import io
import sys
import aio_pika
from minio import Minio

# --- PARCHE DE RUTAS ---
if "/app" not in sys.path:
    sys.path.append("/app")

# --- IMPORTS DE DOMINIO ---
from src.services.learning.domain.entities import (
    ExamConfig, ExamDifficulty, CognitiveType,
    PedagogicalPattern
)
# --- IMPORTS DE LÓGICA ---
from src.services.learning.logic.exam_generator import ExamGenerator
from src.services.learning.logic.content_selector import ContentSelector
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.blueprint import ExamBlueprintBuilder
from src.services.learning.infrastructure.pdf_renderer import PDFRenderer

# --- IMPORTS DE INFRAESTRUCTURA ---
from src.shared.vectordb.qdrant import QdrantService
from src.services.ai.service import AIService 
from src.shared.database.repositories import PatternRepository, TopicMasteryRepository

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [ExamWorker] %(message)s')
logger = logging.getLogger("ExamWorker")

# ==============================================================================
#  MOCKS DE REPOSITORIOS (Simuladores para Fase 3)
# ==============================================================================

class MockPatternRepository(PatternRepository):
    async def find_patterns(self, scope, **kwargs):
        return []

class MockMasteryRepository(TopicMasteryRepository):
    async def get_weakest_topics(self, student_id, course_id, limit=5):
        return [{"topic": "Dinámica de la Partícula", "mastery": 0.2, "failures": 3}]

    async def get_all_topics(self, course_id):
        return ["Cinemática", "Dinámica", "Trabajo y Energía"]

# ==============================================================================
#  WORKER PRINCIPAL
# ==============================================================================

class ExamGenerationWorker:
    def __init__(self):
        # 1. Configuración de RabbitMQ & MinIO
        self.rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@rabbitmq:5672/')
        
        # MinIO
        self.minio = Minio(
            os.getenv('MINIO_ENDPOINT', 'minio:9000'),
            access_key=os.getenv('MINIO_USER', 'REDACTED'),
            secret_key=os.getenv('MINIO_PASSWORD', 'REDACTED'),
            secure=False
        )
        self.bucket_name = "generated-exams"
        try:
            if not self.minio.bucket_exists(self.bucket_name):
                self.minio.make_bucket(self.bucket_name)
        except Exception as e:
            logger.warning(f"[WARNING] No se pudo conectar a MinIO al inicio: {e}")

        # 2. INYECCIÓN DE DEPENDENCIAS
        logger.info("🧠 Inicializando Core de Ingeniería (Modo Testing)...")
        
        self.ai_service = AIService() 
        self.qdrant = QdrantService()
        self.pattern_repo = MockPatternRepository()
        self.mastery_repo = MockMasteryRepository()
        
        self.content_selector = ContentSelector(self.mastery_repo, self.qdrant, self.ai_service)
        self.style_selector = StyleSelector(self.pattern_repo)
        self.blueprint_builder = ExamBlueprintBuilder()
        
        self.generator = ExamGenerator(
            content_selector=self.content_selector, 
            style_selector=self.style_selector, 
            ai_service=self.ai_service,
            blueprint_builder=self.blueprint_builder
        )
        
        self.renderer = PDFRenderer()

    async def process_job(self, message: aio_pika.IncomingMessage):
        # CORRECCIÓN DE INDENTACIÓN AQUÍ
        async with message.process():
            try:
                data = json.loads(message.body)
                task_id = data.get('task_id')
                student_id = data.get('student_id')
                course_id = data.get('course_id')
                
                logger.info(f"⚡ [Task {task_id}] Procesando solicitud para: {course_id}")

                # ========== CONVERSIÓN SEGURA DE ENUMS ==========
                
                # A. Dificultad
                difficulty_str = data.get('difficulty', 'applied')
                target_difficulty = ExamDifficulty.APPLIED  # Default
                try:
                    # Intenta convertir el string a Enum
                    for diff in ExamDifficulty:
                        if diff.value == difficulty_str:
                            target_difficulty = diff
                            break
                except Exception as e:
                    logger.warning(f"⚠️ Dificultad inválida '{difficulty_str}', usando APPLIED: {e}")

                # B. Tipo Cognitivo
                cog_type_str = data.get('cognitive_type', 'computational')
                cognitive_type = CognitiveType.COMPUTATIONAL  # Default
                try:
                    if cog_type_str == 'conceptual':
                        cognitive_type = CognitiveType.CONCEPTUAL
                    elif cog_type_str == 'design':
                        cognitive_type = CognitiveType.DESIGN_ANALYSIS
                    elif cog_type_str == 'debugging':
                        cognitive_type = CognitiveType.DEBUGGING
                except Exception as e:
                    logger.warning(f"⚠️ Tipo cognitivo inválido '{cog_type_str}', usando COMPUTATIONAL: {e}")

                # C. Patrón Pedagógico
                pattern_str = data.get('pattern', 'adaptive')
                pattern = PedagogicalPattern.ADAPTIVE  # Default
                try:
                    if pattern_str == 'spiral':
                        pattern = PedagogicalPattern.SPIRAL
                    elif pattern_str == 'scaffolding':
                        pattern = PedagogicalPattern.SCAFFOLDING
                except Exception as e:
                    logger.warning(f"⚠️ Patrón inválido '{pattern_str}', usando ADAPTIVE: {e}")

                # ========== CREACIÓN DEL CONFIG (CON ENUMS YA CONVERTIDOS) ==========
                config = ExamConfig(
                    student_id=student_id,
                    course_id=course_id,
                    target_difficulty=target_difficulty,  # ✅ Ya es Enum
                    pattern=pattern,  # ✅ Ya es Enum
                    num_questions=data.get('num_questions', 5),
                    include_code_questions=data.get('include_code', False),
                    topics_include=data.get('topics', [])
                )

                # B. GENERACIÓN
                logger.info(f"⚙️  [Task {task_id}] Generando preguntas...")
                exam_entity = await self.generator.generate_exam(config)
                
                # C. RENDERIZADO
                logger.info(f"🎨 [Task {task_id}] Renderizando PDF...")
                pdf_bytes = self.renderer.render_to_bytes(exam_entity)
                
                # D. ALMACENAMIENTO
                filename = f"{student_id}/{course_id}/{task_id}.pdf"
                pdf_stream = io.BytesIO(pdf_bytes)
                
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: self.minio.put_object(
                    self.bucket_name,
                    filename,
                    pdf_stream,
                    len(pdf_bytes),
                    content_type="application/pdf"
                ))

                logger.info(f"✅ [Task {task_id}] EXITO FINAL. PDF guardado en {self.bucket_name}")

            except Exception as e:
                logger.error(f"🔥 [Task {task_id}] ERROR CRITICO: {e}", exc_info=True)

    async def run(self):
        # Lógica de conexión con reintentos
        connection = await aio_pika.connect_robust(self.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        
        # --- CONFIGURACIÓN ROBUSTA (Igualando al Gateway) ---
        # 1. Aseguramos que existe el mecanismo de Dead Letter (DLX)
        dlx = await channel.declare_exchange('dlx', aio_pika.ExchangeType.DIRECT)
        dlq = await channel.declare_queue("exam.generate.dlq", durable=True)
        await dlq.bind(dlx, routing_key='failed_task')

        # 2. Declaramos la cola principal con los MISMOS argumentos que el Gateway
        queue_args = {
            'x-dead-letter-exchange': 'dlx',
            'x-dead-letter-routing-key': 'failed_task',
            'x-message-ttl': 300000  # 5 minutos
        }
        
        # Declaramos la cola con argumentos
        queue = await channel.declare_queue(
            "exam.generate.job", 
            durable=True, 
            arguments=queue_args
        )
        logger.info("🚀 Worker escuchando peticiones en 'exam.generate.job' (Modo Robusto: TTL+DLQ)...")
        
        await queue.consume(self.process_job)
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(ExamGenerationWorker().run())
    except KeyboardInterrupt:
        pass