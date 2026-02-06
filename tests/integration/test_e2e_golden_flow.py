import pytest
import httpx
import time
import uuid
import logging
import os
import json  # <--- Nuevo import para imprimir bonito

# --- CONFIGURACIÓN ---
BASE_URL = "http://localhost:8000"
TIMEOUT = 30.0
MAX_RETRIES_EXAM = 40  
POLL_INTERVAL = 2

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("E2E-FULL")

PDF_PATH = "tests/assets/contexto_examen.pdf"

@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
        yield c

@pytest.fixture(scope="module")
def user_data():
    unique_id = str(uuid.uuid4())[:8]
    return {
        "email": f"student_{unique_id}@tutor-ia.com",
        "password": "REDACTED",
        "full_name": "E2E Student"
    }

@pytest.fixture(scope="module")
def auth_headers(client, user_data):
    # 1. Registro
    logger.info(f"👤 Registrando: {user_data['email']}")
    resp = client.post("/auth/register", json=user_data)
    assert resp.status_code == 201
    
    # 2. Login
    resp = client.post("/auth/token", data={"username": user_data["email"], "password": user_data["password"]})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_full_learning_cycle(client, auth_headers, user_data):
    """
    FLUJO DE CALIDAD: Registro -> Crear Curso (Service) -> Subir PDF -> Generar -> Submit (Strict Schema)
    """
    
    # --- PASO 0.5: CREAR CURSO ---
    logger.info("📚 Paso 0.5: Creando asignatura 'Física E2E'...")
    course_payload = {
        "name": "Física E2E",
        "domain_field": "physics", 
        "semester": 1,
        "color_theme": "#FF5733"
    }
    resp = client.post("/api/v1/learning/courses", json=course_payload, headers=auth_headers)
    assert resp.status_code == 201, f"Fallo al crear curso: {resp.text}"
    
    course_data = resp.json()
    course_id = course_data.get("id")
    logger.info(f"✅ Curso creado: {course_id}")

    # --- PASO 1: SUBIR PDF ---
    logger.info("📤 Paso 1: Subiendo PDF vinculado...")
    
    # Asegurar que existe un PDF de prueba
    if not os.path.exists(PDF_PATH):
        os.makedirs("tests/assets", exist_ok=True)
        with open(PDF_PATH, "wb") as f:
            f.write(b"%PDF-1.4 dummy content for testing purposes")

    with open(PDF_PATH, "rb") as f:
        files = {"file": ("apuntes.pdf", f, "application/pdf")}
        data = {"course_id": str(course_id)} 
        
        resp = client.post("/api/v1/documents/upload", files=files, data=data, headers=auth_headers)

        # Debug rápido para ver qué nos devuelve el upload
        # print(f"\n🐛 DEBUG UPLOAD RESPONSE: {resp.json()}")
    
    assert resp.status_code in [200, 201, 202], f"Error subida: {resp.text}"
    doc_data = resp.json()
    
    # Leemos el ID sea cual sea el nombre que devuelva el backend
    doc_id = doc_data.get("id") or doc_data.get("document_id") or doc_data.get("job_id")
    
    assert doc_id is not None, "❌ No se recibió un ID de documento válido"
    logger.info(f"✅ PDF Subido. Ref: {doc_id}")

    # --- PARCHE DE ESPERA ---
    logger.warning("⚠️ Esperando 2s para asegurar consistencia (DB)...")
    time.sleep(2) 

    # --- PASO 2: GENERAR EXAMEN ---
    logger.info("🧠 Paso 2: Solicitando examen...")
    payload = {
        "document_id": str(doc_id), 
        "course_id": str(course_id), 
        "topic": "Cinemática Básica",
        "difficulty": "medium",
        "num_questions": 1 
    }
    
    resp = client.post("/api/v1/learning/exams/generate", json=payload, headers=auth_headers)
    assert resp.status_code in [200, 201, 202], f"Error generation: {resp.text}"
    
    task_id = resp.json().get("task_id") 
    logger.info(f"✅ Task ID: {task_id}")

    # --- PASO 3: POLLING (Simulado) ---
    logger.info("⏳ Paso 3: Polling status...")
    resp = client.get(f"/api/v1/learning/exams/status/{task_id}", headers=auth_headers)
    assert resp.status_code == 200

    # Usamos un ID falso porque estamos probando contra el Mock
    fake_exam_id = str(uuid.uuid4())
    logger.info(f"✅ (Simulado) Examen listo. ID: {fake_exam_id}")

    # --- PASO 4: SUBMIT (CORRECCIÓN) ---
    logger.info("📝 Paso 4: Enviando respuestas...")
    
    # Respuestas del alumno (Acertando la pregunta 'q1' del mock)
    answers_list = [
        {
            "question_id": "q1", 
            "numeric_value": 20.0, 
        }
    ]

    submit_payload = {
        "exam_id": fake_exam_id,
        "answers": answers_list
    }
    
    resp = client.post("/api/v1/learning/exams/submit", json=submit_payload, headers=auth_headers)
    
    if resp.status_code != 200:
        logger.error(f"Submit falló: {resp.text}")
    
    assert resp.status_code == 200
    result = resp.json()
    
    # --- VISUALIZACIÓN DEL RESULTADO ---
    print("\n" + "="*60)
    print(f"🎓 BOLETÍN DE RESULTADOS (Examen ID: {fake_exam_id})")
    print("="*60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("="*60 + "\n")
    
    # Validaciones finales
    assert result["total_score"] >= 90.0, "El grader debería dar nota alta (100 idealmente)"
    assert "q1" in result["details"], "Los detalles deben ser un diccionario con las IDs de pregunta"