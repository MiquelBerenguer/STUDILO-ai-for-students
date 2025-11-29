from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

# --- MODELOS DE DATOS ---

class TopicMastery(BaseModel):
    topic_tag: str
    mastery_level: int # 0-100
    consecutive_failures: int
    last_reviewed_at: Optional[datetime] = None

class ContentSuggestion(BaseModel):
    topic_tag: str
    reason: str # "Has fallado mucho", "Repaso rutinario", "Nuevo tema"
    priority_score: float

# --- EL ALGORITMO SELECTOR ---

class ContentSelector:
    """
    Decide QUÉ tema específico rellenará un hueco de estudio.
    Prioridad: Debilidades > Olvidos > Orden natural.
    """
    
    def select_best_topic(self, exam_topics: List[str], mastery_records: List[TopicMastery]) -> ContentSuggestion:
        
        # Convertimos la lista de mastery a un diccionario para búsqueda rápida
        mastery_map = {m.topic_tag: m for m in mastery_records}
        
        suggestions = []
        
        for topic in exam_topics:
            record = mastery_map.get(topic)
            
            # --- CÁLCULO DE PRIORIDAD (La "Salsa Secreta") ---
            score = 1.0
            reason = "Repaso general del temario"
            
            if record:
                # 1. CRITERIO DE DEBILIDAD (El más importante según Plan de Negocio)
                if record.consecutive_failures > 0:
                    # Multiplicador agresivo: Si fallas, la prioridad se dispara.
                    # 1 fallo -> x3, 2 fallos -> x5, 3 fallos -> x7...
                    boost = 1 + (record.consecutive_failures * 2)
                    score *= boost
                    reason = f"¡Alerta! Has fallado {record.consecutive_failures} veces seguidas."
                
                # 2. CRITERIO DE MAESTRÍA (Si ya eres experto, baja la prioridad)
                if record.mastery_level > 80:
                    score *= 0.2 # Baja al 20% de importancia
                    reason = "Ya dominas este tema (Mantenimiento)"
                
                # 3. CRITERIO DE OLVIDO (Simplificado)
                # Si hace mucho que no lo ves, sube un poco la prioridad
                if record.last_reviewed_at:
                    days_since = (datetime.now() - record.last_reviewed_at).days
                    if days_since > 7:
                        score *= 1.5
                        reason += " (Hace tiempo que no lo repasas)"
            
            else:
                # Si no hay registro, es un tema NUEVO. Tiene prioridad media-alta.
                score = 2.0 
                reason = "Tema nuevo sin estudiar"
            
            suggestions.append(ContentSuggestion(
                topic_tag=topic,
                reason=reason,
                priority_score=score
            ))
        
        # ORDENAR: El de mayor score gana
        # Si no hay temas, devolvemos None
        if not suggestions:
            return None
            
        best_topic = sorted(suggestions, key=lambda x: x.priority_score, reverse=True)[0]
        return best_topic