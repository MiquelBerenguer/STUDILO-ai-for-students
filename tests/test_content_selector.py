from datetime import datetime, timedelta
from src.services.learning.content_selector import ContentSelector, TopicMastery

def test_weakness_priority():
    selector = ContentSelector()
    
    # ESCENARIO:
    # El examen tiene 3 temas: Matrices, Vectores, Geometría.
    syllabus = ["Matrices", "Vectores", "Geometría"]
    
    # HISTORIAL DEL ALUMNO:
    # - Matrices: Un desastre (3 fallos seguidos).
    # - Vectores: Un genio (90% maestría).
    # - Geometría: Ni lo ha mirado (No hay registro).
    records = [
        TopicMastery(topic_tag="Matrices", mastery_level=20, consecutive_failures=3),
        TopicMastery(topic_tag="Vectores", mastery_level=90, consecutive_failures=0)
    ]
    
    # EJECUCIÓN
    result = selector.select_best_topic(syllabus, records)
    
    print("\n--- RESULTADO DEL SELECTOR ---")
    print(f"Ganador: {result.topic_tag}")
    print(f"Razón: {result.reason}")
    print(f"Score: {result.priority_score}")
    
    # VERIFICACIÓN
    # Matrices debería ganar por goleada (Score base 1 * Boost (1 + 3*2) = 7.0)
    # Geometría tendría score 2.0 (Nuevo)
    # Vectores tendría score 0.2 (Experto)
    
    if result.topic_tag == "Matrices" and result.priority_score >= 7.0:
        print("✅ ÉXITO: El sistema detectó la debilidad crítica.")
    else:
        print("❌ FALLO: No priorizó el tema fallado.")

if __name__ == "__main__":
    test_weakness_priority()