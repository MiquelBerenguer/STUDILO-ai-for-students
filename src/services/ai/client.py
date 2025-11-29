from abc import ABC, abstractmethod
import json

# 1. LA INTERFAZ
class AIService(ABC):
    @abstractmethod
    async def generate_text(self, prompt: str, model: str = "fast") -> str:
        pass

    @abstractmethod
    async def generate_json(self, prompt: str, schema: dict, model: str = "smart") -> dict:
        pass

# 2. EL MOCK (Corregido para evitar KeyError)
class MockAIService(AIService):
    
    async def generate_text(self, prompt: str, model: str = "fast") -> str:
        return "procedural" # Simula detección de tipo cognitivo

    async def generate_json(self, prompt: str, schema: dict, model: str = "smart") -> dict:
        print(f"[MOCK AI] Recibido prompt para JSON (Modelo: {model})")
        
        # IMPORTANTE: Estas claves deben coincidir EXACTAMENTE con lo que pide ExamGenerator
        return {
            "question_text": "¿Si la velocidad se duplica, qué pasa con la energía cinética?",
            "options": ["Se duplica", "Se cuadruplica", "Sigue igual", "Se reduce"],
            "correct_answer": "Se cuadruplica",
            "explanation": "La energía cinética depende del cuadrado de la velocidad (1/2 mv^2).",
            # Añadimos claves extra por si acaso, aunque el generador no las use todas ahora
            "cognitive_level": "analysis"
        }