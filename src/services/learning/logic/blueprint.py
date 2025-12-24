import math
import random
from typing import List, Dict, Optional
from pydantic import BaseModel, Field # <--- CAMBIO CRÍTICO: Usamos Pydantic

from src.services.learning.domain.entities import (
    ExamConfig, ExamDifficulty, CognitiveType, PedagogicalPattern
)

# [Visualización] Matriz de Distribución Cognitiva (TU GRAN APORTE)
COGNITIVE_MATRIX = {
    # Ingeniería pura (Cálculo, Física, Programación)
    "technical": {
        ExamDifficulty.FUNDAMENTAL: [CognitiveType.CONCEPTUAL, CognitiveType.COMPUTATIONAL],
        ExamDifficulty.APPLIED:     [CognitiveType.COMPUTATIONAL, CognitiveType.DEBUGGING],
        ExamDifficulty.COMPLEX:     [CognitiveType.DESIGN_ANALYSIS, CognitiveType.DEBUGGING],
        ExamDifficulty.GATEKEEPER:  [CognitiveType.DESIGN_ANALYSIS]
    },
    # Gestión o Humanidades (Ética, Historia de la Ingeniería)
    "theoretical": {
        ExamDifficulty.FUNDAMENTAL: [CognitiveType.CONCEPTUAL],
        ExamDifficulty.APPLIED:     [CognitiveType.CONCEPTUAL, CognitiveType.DESIGN_ANALYSIS],
        ExamDifficulty.COMPLEX:     [CognitiveType.DESIGN_ANALYSIS],
        ExamDifficulty.GATEKEEPER:  [CognitiveType.DESIGN_ANALYSIS]
    }
}

# --- ENTIDAD DE DOMINIO (ADAPTADA A PYDANTIC) ---
class ExamSlot(BaseModel):
    """Representa un 'hueco' en el examen que luego la IA rellenará"""
    slot_index: int
    difficulty: ExamDifficulty
    topic_id: str
    points: float
    cognitive_target: CognitiveType

class ExamBlueprintBuilder:
    def __init__(self):
        # Configuración base de puntos
        self.base_points = {
            ExamDifficulty.FUNDAMENTAL: 1.0,
            ExamDifficulty.APPLIED: 1.5,
            ExamDifficulty.COMPLEX: 2.5,
            ExamDifficulty.GATEKEEPER: 4.0
        }

    def create_blueprint(self, config: ExamConfig, available_topics: List[str]) -> List[ExamSlot]:
        """
        Crea un plan de examen equilibrado, variando temas y tipos cognitivos.
        """
        total_questions = config.num_questions
        if total_questions <= 0: return []

        # 1. CALCULAR DISTRIBUCIÓN DE DIFICULTAD
        difficulty_counts = self._calculate_difficulty_distribution(total_questions, config.target_difficulty)
        
        # Aplanamos la lista (Ej: [Easy, Easy, Medium, Hard...])
        slot_difficulties = []
        for diff, count in difficulty_counts.items():
            slot_difficulties.extend([diff] * count)
        
        # Ordenamos por dificultad ascendente (Curva de aprendizaje estándar)
        # Esto implementa implícitamente un patrón "Adaptive/Linear"
        slot_difficulties.sort(key=lambda x: self.base_points.get(x, 0))

        slots = []
        raw_total_points = 0.0

        # Si no hay temas disponibles, fallback
        if not available_topics:
            available_topics = ["General Engineering"]

        # 2. ASIGNACIÓN INTELIGENTE (Topics & Cognitive)
        for i, difficulty in enumerate(slot_difficulties):
            
            # A. Selección de Tema (Ponderada)
            topic = self._select_topic_weighted(available_topics, config.topics_include, i)
            
            # B. Selección Cognitiva (Usando tu Matriz)
            # Por defecto asumimos 'technical' para ingeniería
            cog_type = self._select_cognitive_type(difficulty, mode="technical")

            raw_pts = self.base_points.get(difficulty, 1.0)
            raw_total_points += raw_pts

            slots.append(ExamSlot(
                slot_index=i + 1,
                difficulty=difficulty,
                topic_id=topic,
                points=raw_pts, # Se ajustará en el paso 3
                cognitive_target=cog_type
            ))

        # 3. NORMALIZACIÓN DE PUNTUACIÓN (Target: 10.0)
        target_score = 10.0
        scale_factor = target_score / raw_total_points if raw_total_points > 0 else 1.0
        
        current_sum = 0.0
        for slot in slots:
            slot.points = round(slot.points * scale_factor, 2)
            current_sum += slot.points
            
        # Ajuste del último decimal para exactitud perfecta
        diff = target_score - current_sum
        if slots and abs(diff) > 0.001:
            slots[-1].points = round(slots[-1].points + diff, 2)

        return slots

    def _calculate_difficulty_distribution(self, n_questions: int, target: ExamDifficulty) -> Dict[ExamDifficulty, int]:
        """Define cuántas preguntas de cada tipo según la dificultad global deseada"""
        
        # Ratios definidos como porcentajes (TU LÓGICA)
        ratios = {
            ExamDifficulty.FUNDAMENTAL: { # Examen Fácil
                ExamDifficulty.FUNDAMENTAL: 0.6, 
                ExamDifficulty.APPLIED: 0.3, 
                ExamDifficulty.COMPLEX: 0.1,
                ExamDifficulty.GATEKEEPER: 0.0
            },
            ExamDifficulty.APPLIED: { # Examen Estándar
                ExamDifficulty.FUNDAMENTAL: 0.2, 
                ExamDifficulty.APPLIED: 0.5, 
                ExamDifficulty.COMPLEX: 0.3,
                ExamDifficulty.GATEKEEPER: 0.0
            },
            ExamDifficulty.COMPLEX: { # Examen Difícil
                ExamDifficulty.FUNDAMENTAL: 0.1, 
                ExamDifficulty.APPLIED: 0.3, 
                ExamDifficulty.COMPLEX: 0.4,
                ExamDifficulty.GATEKEEPER: 0.2
            },
            ExamDifficulty.GATEKEEPER: { # Modo "Dios"
                ExamDifficulty.FUNDAMENTAL: 0.0, 
                ExamDifficulty.APPLIED: 0.2, 
                ExamDifficulty.COMPLEX: 0.4,
                ExamDifficulty.GATEKEEPER: 0.4
            }
        }
        
        selected_ratios = ratios.get(target, ratios[ExamDifficulty.APPLIED])
        
        distribution = {}
        assigned_count = 0
        
        # Asignar base
        for diff, ratio in selected_ratios.items():
            count = math.floor(n_questions * ratio)
            distribution[diff] = count
            assigned_count += count
            
        # Repartir el remanente a la categoría dominante (target)
        remainder = n_questions - assigned_count
        if remainder > 0:
            distribution[target] = distribution.get(target, 0) + remainder
            
        return distribution

    def _select_topic_weighted(self, available: List[str], focus: List[str], index: int) -> str:
        """
        Da prioridad a los temas de foco (60%), pero no olvida el resto.
        """
        if not available: return "General"
        
        # Si hay focus topics, los usamos en índices pares (0, 2, 4...)
        if focus and len(focus) > 0:
            if index % 2 == 0:
                return focus[index % len(focus)]
        
        # Si no, rotamos sobre todos los disponibles
        return available[index % len(available)]

    def _select_cognitive_type(self, difficulty: ExamDifficulty, mode: str = "technical") -> CognitiveType:
        """Selecciona el tipo cognitivo usando la Matriz y un poco de aleatoriedad controlada"""
        options = COGNITIVE_MATRIX.get(mode, COGNITIVE_MATRIX["technical"]).get(difficulty)
        
        if not options:
            return CognitiveType.COMPUTATIONAL # Fallback seguro
            
        return random.choice(options)