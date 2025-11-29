import asyncio
from src.services.learning.domain.entities import ExamConfig, ExamDifficulty
from src.services.learning.logic.exam_generator import ExamGenerator
from src.services.learning.logic.content_selector import ContentSelector
from src.services.learning.logic.style_selector import StyleSelector
from src.services.ai.client import MockAIService # Usamos el Mock por ahora

# Mocks rápidos para Repositorios (Simulamos la Base de Datos)
class MockTopicMasteryRepo:
    async def get_weakest_topics(self, student_id, course_id):
        return [] # Simula que no hay debilidades previas
    async def get_all_topics(self, course_id):
        return ["Aerodinámica", "Mecánica de Fluidos", "Propulsión"]

class MockVectorDB:
    async def search(self, query, filters, limit):
        # Simula encontrar un trozo de apunte
        from dataclasses import dataclass
        @dataclass
        class Chunk: text: str
        return [Chunk(text=f"Texto simulado sobre {filters.get('topic_id')}... la ecuación fundamental es F=ma...")]

class MockPatternRepo:
    async def find_patterns(self, scope, cognitive_type=None, difficulty=None, target_id=None):
        return None # Simula que aun no hemos subido exámenes viejos (usará fallback)

async def main():
    print("🚀 INICIANDO TEST DE SISTEMA DE EXÁMENES...")

    # 1. INICIALIZACIÓN DE DEPENDENCIAS (Wiring)
    # Aquí conectamos los cables como haría el servidor real
    mock_ai = MockAIService()
    mock_db = MockTopicMasteryRepo()
    mock_vector = MockVectorDB()
    mock_pattern = MockPatternRepo()

    content_selector = ContentSelector(mock_db, mock_vector, mock_ai)
    style_selector = StyleSelector(mock_pattern)
    
    # EL MOTOR PRINCIPAL
    generator = ExamGenerator(content_selector, style_selector, mock_ai)

    # 2. DEFINIR EL PEDIDO DEL ALUMNO
    config = ExamConfig(
        student_id="student_123",
        course_id="course_aero_01",
        num_questions=10,  # ¡QUEREMOS 10 PREGUNTAS!
        difficulty=ExamDifficulty.HARD # ¡MODO DIFÍCIL!
    )

    # 3. EJECUTAR GENERACIÓN
    try:
        exam = await generator.generate_exam(config)
        
        print(f"\n✅ ¡ÉXITO! Examen Generado ID: {exam.id}")
        print(f"📊 Configuración: {len(exam.questions)} preguntas | Nivel: {config.difficulty.name}")
        print("-" * 60)
        
        # 4. IMPRIMIR RESULTADOS
        total_points = 0
        for i, q in enumerate(exam.questions):
            # Extraemos los puntos del texto de explicación (un hack visual para el test)
            points_str = q.explanation.split(']')[0].replace('[Valor: ', '').replace(' pts', '')
            print(f"[{i+1}] [{points_str} pts] {q.question_text}")
            print(f"    R: {q.correct_answer}")
            print(f"    Estilo: {q.used_pattern_id}")
            print("-" * 20)
            
    except Exception as e:
        print(f"❌ ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())