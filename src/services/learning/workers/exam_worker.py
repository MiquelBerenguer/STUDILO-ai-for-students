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
    ExamConfig, ExamDifficulty, CognitiveType
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
# Importamos solo las INTERFACES (los contratos)
from src.shared.database.repositories import PatternRepository, TopicMasteryRepository

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [ExamWorker] %(message)s')
logger = logging.getLogger("ExamWorker")

# ==============================================================================
#  MOCKS DE REPOSITORIOS (Simuladores para Fase 3)
#  Esto permite que el sistema funcione sin Base de Datos real conectada aún.
# ==============================================================================

class MockPatternRepository(PatternRepository):
    """Simula buscar patrones pedagógicos en la DB."""
    async def find_patterns(self, scope, **kwargs):
        # Retornamos una lista vacía o un patrón por defecto simulado si fuera necesario.
        # El StyleSelector sabrá manejar esto y usará un default.
        return []

class MockMasteryRepository(TopicMasteryRepository):
    """Simula conocer qué temas lleva mal el alumno."""
    async def get_weakest_topics(self, student_id, course_id, limit=5):
        # Simulamos que el alumno falla en "Dinámica"
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
        
        # MinIO con reintentos básicos de conexión si hiciera falta
        self.minio = Minio(
            os.getenv('MINIO_ENDPOINT', 'minio:9000'),
            access_key=os.getenv('MINIO_USER', 'REDACTED'),
            secret_key=os.getenv('MINIO_PASSWORD', 'REDACTED'),
            secure=False
        )
        self.bucket_name = "generated-exams"
        # Intentamos crear el bucket (puede fallar si MinIO no está listo, lo manejamos)
        try:
            if not self.minio.bucket_exists(self.bucket_name):
                self.minio.make_bucket(self.bucket_name)
        except Exception as e:
            logger.warning(f"[WARNING] No se pudo conectar a MinIO al inicio: {e}")

        # 2. INYECCIÓN DE DEPENDENCIAS (Ensamblaje con MOCKS)
        logger.info("🧠 Inicializando Core de Ingeniería (Modo Testing)...")
        
        # Servicios Base (Mockeados para Fase 3)
        self.ai_service = AIService() 
        self.qdrant = QdrantService()
        
        # Repositorios (USAMOS LOS MOCKS AQUÍ)
        self.pattern_repo = MockPatternRepository()     # <--- CORREGIDO
        self.mastery_repo = MockMasteryRepository()     # <--- CORREGIDO
        
        # Piezas Lógicas
        self.content_selector = ContentSelector(self.mastery_repo, self.qdrant, self.ai_service)
        self.style_selector = StyleSelector(self.pattern_repo)
        self.blueprint_builder = ExamBlueprintBuilder()
        
        # El Generador
        self.generator = ExamGenerator(
            content_selector=self.content_selector, 
            style_selector=self.style_selector, 
            ai_service=self.ai_service,
            blueprint_builder=self.blueprint_builder
        )
        
        self.renderer = PDFRenderer()

    async def process_job(self, message: aio_pika.IncomingMessage):
        async with message.process():
            try:
                data = json.loads(message.body)
                task_id = data.get('task_id')
                student_id = data.get('student_id')
                course_id = data.get('course_id')
                
                logger.info(f"⚡ [Task {task_id}] Procesando solicitud para: {course_id}")

                # A. Configuración
                # Fallback seguro para cognitive_type (default a COMPUTATIONAL)
                cog_type_str = data.get('cognitive_type', 'computational')
                # Mapeo manual simple por seguridad
                cog_type = CognitiveType.COMPUTATIONAL
                if cog_type_str == 'conceptual': cog_type = CognitiveType.CONCEPTUAL
                elif cog_type_str == 'design': cog_type = CognitiveType.DESIGN_ANALYSIS
                
                config = ExamConfig(
                    student_id=student_id,
                    course_id=course_id,
                    target_difficulty=ExamDifficulty(data.get('difficulty', 'applied')),
                    pattern=None, # Dejamos que el StyleSelector elija
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
        
        queue = await channel.declare_queue("exam.generate.job", durable=True)
        logger.info("🚀 Worker escuchando peticiones en 'exam.generate.job'...")
        
        await queue.consume(self.process_job)
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(ExamGenerationWorker().run())
    except KeyboardInterrupt:
        pass