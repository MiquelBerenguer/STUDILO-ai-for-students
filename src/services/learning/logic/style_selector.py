import random
from typing import Optional
from src.services.learning.domain.entities import (
    PedagogicalPattern, CognitiveType, ExamDifficulty, PatternScope
)
from src.shared.database.repositories import PatternRepository

class StyleSelector:
    def __init__(self, pattern_repo: PatternRepository):
        # Inyección de dependencia correcta.
        self.pattern_repo = pattern_repo

    async def select_best_pattern(
        self, 
        course_id: str, 
        domain: str, 
        cognitive_needed: CognitiveType, 
        difficulty: ExamDifficulty
    ) -> Optional[PedagogicalPattern]:
        """
        Algoritmo de Cascada (Waterfall Strategy):
        Prioriza la personalización extrema (Curso) sobre la generalización (Global).
        """
        try:
            # 1. NIVEL: Hiper-específico (Estilo del profesor de este curso)
            # Esto cumple con "Aislamiento de Contexto" [cite: 339]
            course_patterns = await self.pattern_repo.find_patterns(
                scope=PatternScope.COURSE,
                target_id=course_id,
                cognitive_type=cognitive_needed,
                difficulty=difficulty
            )
            if course_patterns:
                # Retornamos uno al azar para variar los exámenes y no ser repetitivos
                return random.choice(course_patterns)
            
            # 2. NIVEL: Dominio (Ej. Ingeniería Aeroespacial)
            # Si no hay datos del curso, usamos el estándar de la industria.
            domain_patterns = await self.pattern_repo.find_patterns(
                scope=PatternScope.DOMAIN,
                target_id=domain,
                cognitive_type=cognitive_needed,
                difficulty=difficulty
            )
            if domain_patterns:
                return random.choice(domain_patterns)
            
            # 3. NIVEL: Fallback Global (Pedagogía General)
            # Último recurso para asegurar que siempre devolvemos ALGO.
            global_patterns = await self.pattern_repo.find_patterns(
                scope=PatternScope.GLOBAL,
                target_id=None, # Global no tiene target
                cognitive_type=cognitive_needed,
                difficulty=difficulty
            )
            
            if global_patterns:
                return random.choice(global_patterns)
            
            # 4. EMERGENCIA
            print(f"⚠️ WARNING: No se encontraron patrones para {cognitive_needed} - {difficulty}")
            return None

        except Exception as e:
            # En producción, no queremos que el examen falle solo porque falló el estilo.
            # Logueamos el error y devolvemos None (el generador usará estilo default).
            print(f"❌ Error crítico en StyleSelector: {str(e)}")
            return None