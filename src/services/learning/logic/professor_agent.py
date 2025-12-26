from typing import List, Dict, Any
from src.services.learning.api.schemas import ChatRequest, ChatResponse

class ProfessorAgent:
    def __init__(self):
        # TU ALGORITMO DE PERSONALIDAD (Intacto)
        self.SYSTEM_PROMPT = """
        Eres un "Mentor Ingeniero Senior". Tu objetivo es ayudar a un estudiante de ingeniería a construir sus propios apuntes de alta calidad ("Efecto IKEA").
        
        PERSONALIDAD:
        - Tono: Profesional, cercano, alentador. Autoridad competente.
        - Estilo: Pragmático. Prioriza la intuición física sobre el rigor matemático ciego.
        - Prohibido: Jerga juvenil, formalismo robótico.
        - Obligatorio: Refuerzo positivo específico.

        ALGORITMO DE COMPORTAMIENTO:
        1. CHUNKING: No resumas todo. Agrupa en bloques lógicos. Salta la "paja".
        2. ACTIVE RECALL: Antes de explicar, pregunta: "¿Cómo me explicarías X con tus palabras?".
        3. ANDAMIAJE: 
           - Correcta pero incompleta: Valida y pide matiz.
           - Incorrecta: Redirige al párrafo del PDF.
           - Bloqueo: Usa analogía real (coches, fluidos).
        4. AUTORÍA FINAL: Pídele redactar el párrafo definitivo y verifícalo.

        REGLAS DE ORO:
        - Prioridad Lógica: Primero concepto físico, luego fórmula.
        - Cláusula Pragmática: Si pide "dame la fórmula" explícitamente, OBEDECE.
        """


    async def ask(self, request: ChatRequest) -> ChatResponse:
        """
        Procesa el mensaje aplicando la metodología del Mentor.
        """
        
        # 1. Recuperar contexto (Simulación RAG)
        # Aquí buscaríamos en la Vector DB usando request.context_files
        context_data = "Contenido extraído de los PDFs..." 

        # 2. Llamada al LLM (Simulada por ahora)
        # En el futuro: response = await openai.ChatCompletion.create(...)
        
        # MOCK RESPONSE (Simulando paso 2: Active Recall)
        response_text = (
            "He analizado el PDF. Antes de definir la Entropía, "
            "basándote en la diapositiva 14, ¿cómo explicarías el 'Desorden'?"
        )

        return ChatResponse(
            response=response_text,
            methodology_step="Active Recall / Scaffolding",
            sources=["Diapositiva 14", "Apuntes Tema 3"]
        )

# Instancia Singleton (opcional, pero útil para mantener conexiones DB vivas)
professor_agent = ProfessorAgent()