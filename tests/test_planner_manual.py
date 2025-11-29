from datetime import date, timedelta
from src.services.learning.study_planner import GlobalStudyPlanner, ExamInput, UserPreferences

# --- HERRAMIENTA DE VISUALIZACIÓN ---
def print_schedule(schedule, test_name):
    print(f"\n--- RESULTADO TEST: {test_name} ---")
    if not schedule:
        print("   [VACÍO] No se generaron sesiones.")
        return
    
    # Agrupar por examen para ver horas asignadas
    exam_hours = {}
    for s in schedule:
        exam_hours[s.exam_id] = exam_hours.get(s.exam_id, 0) + s.duration
    
    for exam_id, minutes in exam_hours.items():
        print(f"   Examen {exam_id}: {minutes/60:.1f} horas asignadas.")

# --- CONFIGURACIÓN INICIAL ---
planner = GlobalStudyPlanner()
today = date.today()

# CREAMOS 4 EXÁMENES (Simulando tu escenario de "Cuello de Botella")
exams = [
    # Inminente (Jueves)
    ExamInput(id="EX-CALCULO", name="Cálculo", exam_date=today + timedelta(days=3), difficulty_level=8, topics=["Integrales"]),
    # Cercano (Lunes)
    ExamInput(id="EX-FISICA", name="Física", exam_date=today + timedelta(days=7), difficulty_level=7, topics=["Cinemática"]),
    # Cercano (Martes)
    ExamInput(id="EX-ALGEBRA", name="Álgebra", exam_date=today + timedelta(days=8), difficulty_level=6, topics=["Matrices"]),
    # El 4º en discordia (Jueves siguiente) - DEBERÍA SER BLOQUEADO por defecto
    ExamInput(id="EX-DIBUJO", name="Dibujo", exam_date=today + timedelta(days=10), difficulty_level=5, topics=["Diédrico"]),
]

# Disponibilidad: 2 horas hoy y mañana
availability = {
    str(today): 120,
    str(today + timedelta(days=1)): 120
}

# --- TEST 1: LÓGICA DE SATURACIÓN (Standard) ---
# Esperamos que planifique Cálculo, Física y Álgebra, pero BLOQUEE Dibujo (es el 4º)
prefs_normal = UserPreferences(availability_slots=availability, force_include_ids=[])
schedule_1 = planner.generate_schedule(exams, prefs_normal)
print_schedule(schedule_1, "1. Saturación (Sin Override)")

# Verificación automática
ids_planificados = {s.exam_id for s in schedule_1}
if "EX-DIBUJO" not in ids_planificados and "EX-CALCULO" in ids_planificados:
    print("   ✅ ÉXITO: 'Dibujo' fue bloqueado correctamente por saturación.")
else:
    print("   ❌ FALLO: La lógica de saturación falló.")

# --- TEST 2: LÓGICA DE OVERRIDE (Usuario Manda) ---
# Ahora forzamos "Dibujo". El sistema debe incluirlo aunque estemos saturados.
prefs_forced = UserPreferences(availability_slots=availability, force_include_ids=["EX-DIBUJO"])
schedule_2 = planner.generate_schedule(exams, prefs_forced)
print_schedule(schedule_2, "2. Con Override Activado")

# Verificación automática
ids_planificados_2 = {s.exam_id for s in schedule_2}
if "EX-DIBUJO" in ids_planificados_2:
    print("   ✅ ÉXITO: 'Dibujo' fue incluido forzosamente.")
else:
    print("   ❌ FALLO: El Override no funcionó.")