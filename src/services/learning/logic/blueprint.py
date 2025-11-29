import math
from typing import List, Dict
from dataclasses import dataclass, field
from src.services.learning.domain.entities import (
    ExamConfig, ExamDifficulty, CognitiveType
)

@dataclass
class BlueprintConfig:
    target_score: float = 10.0
    # Puntos base según la dificultad (Fácil vale menos, Difícil vale más)
    base_points: Dict[str, float] = field(default_factory=lambda: {
        "easy": 1.0, 
        "medium": 1.5, 
        "hard": 2.5
    })

@dataclass
class QuestionSlot:
    slot_index: int
    difficulty: ExamDifficulty
    topic_id: str
    points: float  
    # El tipo cognitivo es constante para el examen (según la asignatura)
    cognitive_target: CognitiveType 

class ExamBlueprintBuilder:
    def __init__(self, config: BlueprintConfig = None):
        self.config = config or BlueprintConfig()

    def create_blueprint(self, config: ExamConfig, available_topics: List[str]) -> List[QuestionSlot]:
        """
        Genera la estructura. 
        CAMBIO CLAVE: El CognitiveType viene del Curso (config.course_cognitive_type),
        ya no depende de si la pregunta es fácil o difícil.
        """
        slots = []
        total_questions = config.num_questions
        if total_questions <= 0: return []
        
        # 1. DISTRIBUCIÓN DE DIFICULTAD (Esto se mantiene)
        # Un examen 'Difícil' de Historia tendrá muchas preguntas 'Hard' (Declarativas Complejas)
        if config.difficulty == ExamDifficulty.HARD:
            ratios = {ExamDifficulty.EASY: 0.1, ExamDifficulty.MEDIUM: 0.4, ExamDifficulty.HARD: 0.5}
        elif config.difficulty == ExamDifficulty.EASY:
            ratios = {ExamDifficulty.EASY: 0.6, ExamDifficulty.MEDIUM: 0.3, ExamDifficulty.HARD: 0.1}
        else: 
            ratios = {ExamDifficulty.EASY: 0.3, ExamDifficulty.MEDIUM: 0.5, ExamDifficulty.HARD: 0.2}

        n_easy = math.floor(total_questions * ratios[ExamDifficulty.EASY])
        n_hard = math.floor(total_questions * ratios[ExamDifficulty.HARD])
        n_medium = total_questions - n_easy - n_hard 

        difficulties = (
            [ExamDifficulty.EASY] * n_easy +
            [ExamDifficulty.MEDIUM] * n_medium +
            [ExamDifficulty.HARD] * n_hard
        )
        
        # 2. ASIGNACIÓN
        if not available_topics:
            available_topics = ["general"]
            
        temp_slots = []
        raw_total_points = 0.0

        for i, diff in enumerate(difficulties):
            topic = available_topics[i % len(available_topics)]
            
            raw_pts = self.config.base_points.get(diff.value, 1.0)
            raw_total_points += raw_pts
            
            # --- CORRECCIÓN AQUÍ ---
            # Antes: Calculábamos el tipo según la dificultad.
            # Ahora: Usamos estrictamente el tipo del curso.
            # Un problema fácil de mates es PROCEDURAL. Uno difícil también.
            cog_type = config.course_cognitive_type 
            
            temp_slots.append({
                "index": i + 1,
                "diff": diff,
                "topic": topic,
                "raw_pts": raw_pts,
                "cog": cog_type
            })

        # 3. NORMALIZACIÓN (Suma 10)
        scale_factor = self.config.target_score / raw_total_points if raw_total_points > 0 else 1.0

        for item in temp_slots:
            final_points = round(item["raw_pts"] * scale_factor, 2)
            
            slots.append(QuestionSlot(
                slot_index=item["index"],
                difficulty=item["diff"],
                topic_id=item["topic"],
                points=final_points,
                cognitive_target=item["cog"]
            ))
            
        # Ajuste decimal final
        current_sum = sum(s.points for s in slots)
        diff_sum = self.config.target_score - current_sum
        if slots and abs(diff_sum) > 0.01:
            slots[-1].points = round(slots[-1].points + diff_sum, 2)

        return slots