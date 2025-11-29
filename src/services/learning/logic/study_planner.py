from datetime import date, timedelta
from typing import List, Dict, Optional
from pydantic import BaseModel

# --- 1. CONFIGURACIÓN (Arquitectura Flexible) ---
class PlannerConfig(BaseModel):
    """
    Parámetros que controlan el comportamiento del algoritmo.
    En el futuro, esto se cargará desde la DB por usuario.
    """
    decay_factor: float = 2.0        # Qué tan rápido cae la urgencia (Curva del olvido)
    vol_multiplier: float = 1.0      # Peso de la cantidad de temas
    forced_exam_boost: float = 10.0  # Multiplicador para exámenes forzados (Override)
    max_concurrent_exams: int = 3    # Regla de saturación mental
    min_session_minutes: int = 15    # Tiempo mínimo viable de estudio

# --- 2. MODELOS DE DOMINIO (Entradas/Salidas) ---
class ExamInput(BaseModel):
    id: str
    name: str
    exam_date: date
    difficulty_level: int # 1-10
    topics_count: int = 1 # Usamos count porque la DB nueva normalizada nos da esto fácil

class UserPreferences(BaseModel):
    # Disponibilidad: "2023-11-20" -> 120 minutos
    availability_slots: Dict[str, int]
    force_include_ids: List[str] = []

class SessionOutput(BaseModel):
    exam_id: str
    date: date
    duration: int
    focus_score: float # Métrica para saber qué tan urgente era esta sesión

# --- 3. MOTOR CENTRAL (The Core Engine) ---
class GlobalStudyPlanner:
    def __init__(self, config: PlannerConfig = None):
        # Inyección de Configuración (Patrón de Diseño)
        self.config = config or PlannerConfig()

    def generate_schedule(self, exams: List[ExamInput], prefs: UserPreferences) -> List[SessionOutput]:
        """
        Genera un plan de estudio optimizado basado en urgencia ponderada.
        NOTA: Este método es puro (sin I/O) y CPU-bound.
        """
        schedule = []
        today = date.today()
        
        # A. FILTRADO Y VALIDACIÓN
        future_exams = [e for e in exams if e.exam_date >= today]
        # Ordenamos por fecha inminente
        sorted_exams = sorted(future_exams, key=lambda x: x.exam_date)
        
        if not sorted_exams:
            return []

        # B. SELECCIÓN DE "LOTE ACTIVO" (Saturation Management)
        # No queremos que el alumno estudie para 10 exámenes a la vez.
        active_batch = self._select_active_batch(sorted_exams, prefs)

        # C. DISTRIBUCIÓN (Algoritmo Greedy por Días)
        # Iteramos cronológicamente por los días disponibles del usuario
        for day_str, minutes_available in sorted(prefs.availability_slots.items()):
            current_date = date.fromisoformat(day_str)
            
            if minutes_available < self.config.min_session_minutes:
                continue
            
            # Calcular "Urgencia" de cada examen para ESTE día específico
            weights = {}
            total_weight = 0.0
            
            for exam in active_batch:
                # Si el examen ya pasó o es hoy, saltar (o manejar pánico)
                if exam.exam_date <= current_date: 
                    continue
                
                urgency = self._calculate_urgency(exam, current_date, prefs)
                weights[exam.id] = urgency
                total_weight += urgency
            
            # Repartir el tiempo del día proporcionalmente a la urgencia
            if total_weight > 0:
                for exam in active_batch:
                    if exam.id in weights:
                        # Regla de tres simple ponderada
                        ratio = weights[exam.id] / total_weight
                        minutes_assigned = int(minutes_available * ratio)
                        
                        # Solo agendamos si supera el umbral mínimo de concentración
                        if minutes_assigned >= self.config.min_session_minutes:
                            schedule.append(SessionOutput(
                                exam_id=exam.id,
                                date=current_date,
                                duration=minutes_assigned,
                                focus_score=round(weights[exam.id], 2)
                            ))
                            
        return schedule

    def _select_active_batch(self, sorted_exams: List[ExamInput], prefs: UserPreferences) -> List[ExamInput]:
        """Selecciona qué exámenes entran en la 'Mente Activa' del estudiante."""
        active = []
        if not sorted_exams: return []
        
        # El examen más cercano SIEMPRE entra
        active.append(sorted_exams[0])
        
        for exam in sorted_exams[1:]:
            is_forced = exam.id in prefs.force_include_ids
            is_crowded = len(active) >= self.config.max_concurrent_exams
            
            # Lógica: Si el usuario lo fuerza O tenemos espacio mental, lo metemos
            if is_forced or not is_crowded:
                active.append(exam)
                
        return active

    def _calculate_urgency(self, exam: ExamInput, current_date: date, prefs: UserPreferences) -> float:
        """
        Fórmula de Urgencia Ponderada.
        Urgencia = (Dificultad * Volumen) / (Días Restantes ^ FactorOlvido)
        """
        days_left = (exam.exam_date - current_date).days
        
        # Protección matemática: Si faltan 0 días, es pánico total (0.5 para elevar urgencia)
        if days_left <= 0: days_left = 0.5
        
        numerator = exam.difficulty_level * self.config.vol_multiplier * exam.topics_count
        denominator = days_left ** self.config.decay_factor
        
        base_urgency = numerator / denominator
        
        # Si el usuario marcó "Force Include", multiplicamos la urgencia artificialmente
        if exam.id in prefs.force_include_ids:
            return base_urgency * self.config.forced_exam_boost
            
        return base_urgency