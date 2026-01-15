import asyncio
import logging
import os
from dotenv import load_dotenv

# Cargar variables de entorno (.env) para que la IA tenga la API KEY
load_dotenv()

# Importamos TU servicio real (el que definiste en Task 4.3)
from src.services.ai.service import AIService
from src.services.learning.domain.entities import (
    ExamDifficulty, 
    QuestionType, 
    CognitiveType, 
    Language
)

# Configurar logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BrainTest")

async def test_the_professor():
    print("\n🧪 --- INICIANDO TEST DE CEREBRO (AIService REAL) ---")
    
    # Verificar API Key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: No se encontró OPENAI_API_KEY en el entorno.")
        return

    # 1. Instanciamos el servicio REAL
    try:
        ai_service = AIService() # Usará la config automática
        print("✅ Servicio IA instanciado.")
    except Exception as e:
        print(f"❌ Error instanciando servicio: {e}")
        return

    # 2. Contexto Dummy (Simulando lo que vendría del PDF)
    dummy_rag_context = """
    PRINCIPIO DE ARQUIMEDES:
    Todo cuerpo sumergido total o parcialmente en un fluido en reposo experimenta 
    un empuje vertical hacia arriba igual al peso del fluido desalojado.
    Fórmula: E = Pe * V = pf * g * V
    Donde pf es la densidad del fluido, V el volumen desplazado y g la gravedad (9.8 m/s2).
    """

    print("\n🧠 Enviando solicitud a OpenAI (puede tardar 5-10s)...")
    
    try:
        # 3. Llamada al servicio
        result = await ai_service.generate_exam_question(
            topic="Hidrostática",
            difficulty=ExamDifficulty.APPLIED,
            question_type=QuestionType.NUMERIC_INPUT,
            cognitive_type=CognitiveType.COMPUTATIONAL,
            rag_context=dummy_rag_context,
            language=Language.ES
        )

        # 4. Validación Visual
        print("\n✅ ¡RESPUESTA RECIBIDA!")
        print("=" * 60)
        print(f"📝 Enunciado LaTeX: {result.get('statement_latex')[:100]}...")
        print(f"💭 Razonamiento: {result.get('chain_of_thought')}")
        
        rules = result.get('validation_rules', {})
        if rules:
            print(f"🎯 Solución: {rules.get('correct_value')} (Tol: {rules.get('tolerance_percentage')}%)")
        else:
            print("⚠️ OJO: No llegaron validation_rules")
            
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ FALLO EN LA GENERACIÓN: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_the_professor())