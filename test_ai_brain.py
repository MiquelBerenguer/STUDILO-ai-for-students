import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()
from src.services.ai.service import AIService
from src.services.learning.domain.entities import (
    ExamDifficulty, QuestionType, CognitiveType, Language
)

logging.basicConfig(level=logging.INFO)

async def test_the_professor():
    print("\n🧪 --- INICIANDO TEST DE CEREBRO 2.0 (Schema Updated) ---")
    
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: Falta OPENAI_API_KEY.")
        return

    ai_service = AIService()

    print("🧠 Enviando solicitud a OpenAI...")
    try:
        # Nota: El servicio ahora devuelve el objeto COMPLETO (chain_of_thought + content)
        result_full = await ai_service.generate_exam_question(
            topic="Hidrostática",
            difficulty=ExamDifficulty.APPLIED,
            question_type=QuestionType.NUMERIC_INPUT,
            cognitive_type=CognitiveType.COMPUTATIONAL,
            rag_context="Principio de Arquímedes...",
            language=Language.ES
        )

        print("\n✅ ¡RESPUESTA RECIBIDA Y VALIDADA!")
        print("=" * 60)
        
        # 1. Verificamos el Razonamiento
        cot = result_full.get('chain_of_thought', 'N/A')
        print(f"💭 Razonamiento IA:\n{cot[:150]}...\n")
        
        # 2. Accedemos al contenido real
        content = result_full.get('content', {})
        
        print(f"📝 Enunciado: {content.get('statement_latex')[:100]}...")
        print(f"🔑 Tipo detectado: {content.get('kind')}")

        # 3. Verificación de Datos Numéricos (Schema Plano)
        if content.get('kind') == 'numeric_input':
            sol = content.get('numeric_solution')
            tol = content.get('tolerance_percent')
            print(f"🎯 Solución Numérica: {sol} (Tol: {tol}%)")
            
            if sol is not None:
                print("✅ Validación: Los datos numéricos llegaron correctamente.")
            else:
                print("⚠️ ALERTA: Llegó el tipo correcto pero falta el valor.")
        
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ FALLO: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_the_professor())