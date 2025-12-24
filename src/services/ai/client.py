from abc import ABC, abstractmethod
import json

# 1. LA INTERFAZ (El Contrato)
class AIService(ABC):
    @abstractmethod
    async def generate_text(self, prompt: str, model: str = "fast") -> str:
        pass

    @abstractmethod
    async def generate_json(self, prompt: str, schema: dict, model: str = "smart") -> dict:
        pass

# 2. EL MOCK (El Actor de Doble)
class MockAIService(AIService):
    """
    Simula ser una IA avanzada para pruebas sin gastar dinero en tokens.
    Devuelve estructuras válidas para el Generador de Exámenes de Ingeniería.
    """
    
    async def generate_text(self, prompt: str, model: str = "fast") -> str:
        # Simula un análisis de tema o contexto
        return "El estudiante parece tener dificultades con conceptos termodinámicos."

    async def generate_json(self, prompt: str, schema: dict, model: str = "smart") -> dict:
        print(f"[MOCK AI] Generando JSON simulado para prompt...")
        
        # Detectamos qué pide el prompt para dar una respuesta coherente
        prompt_lower = prompt.lower()
        
        # CASO 1: Pregunta Numérica (Ingeniería estándar)
        if "numeric" in prompt_lower or "numérico" in prompt_lower:
            return {
                "statement_latex": "Una viga de acero de longitud $L=5m$ soporta una carga uniforme $q=10 kN/m$. Calcule el momento máximo.",
                "explanation": "El momento máximo en una viga simplemente apoyada ocurre en el centro y es $M_{max} = qL^2/8$.",
                "numeric_solution": 31.25,
                "tolerance_percent": 2.0,
                "units": ["kN·m", "Nm"],
                "hint": "Recuerda la fórmula de viga biapoyada."
            }
            
        # CASO 2: Código (Programación)
        elif "code" in prompt_lower or "código" in prompt_lower:
            return {
                "statement_latex": "Escribe una función en Python para calcular el factorial de $n$.",
                "explanation": "El factorial se define recursivamente como $n! = n \times (n-1)!$.",
                "code_context": "def factorial(n):",
                "test_cases": [
                    {"input": "5", "output": "120", "hidden": False},
                    {"input": "0", "output": "1", "hidden": True}
                ],
                "hint": "Cuidado con el caso base n=0."
            }

        # CASO 3: Test (Conceptual)
        else:
            return {
                "statement_latex": "¿Cuál es la ley cero de la termodinámica?",
                "explanation": "Define el equilibrio térmico y permite la definición de temperatura.",
                "options": [
                    "Conservación de la energía",
                    "Equilibrio térmico",
                    "Entropía siempre aumenta",
                    "Cero absoluto inalcanzable"
                ],
                "correct_option_index": 1,
                "hint": "Piensa en termómetros."
            }