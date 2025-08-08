#!/usr/bin/env python3
"""
Test Simple API Script
Prueba todos los endpoints de la API simple (puerto 8003)
"""

import requests
import json
import time
from pathlib import Path

# URL base de la API simple
BASE_URL = "http://localhost:8003"

def test_health():
    """Prueba el endpoint de health"""
    print("\n🏥 Probando Health Check...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error conectando: {e}")
        return False

def test_upload():
    """Prueba el endpoint de upload"""
    print("\n📤 Probando Upload de archivo...")
    
    # Crear un archivo PDF de prueba (simulado)
    test_pdf = b"%PDF-1.4\n%Fake PDF content for testing"
    
    files = {
        'file': ('test_document.pdf', test_pdf, 'application/pdf')
    }
    
    try:
        response = requests.post(f"{BASE_URL}/upload", files=files)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return result.get('job_id')
        else:
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error en upload: {e}")
        return None

def test_status(job_id):
    """Prueba el endpoint de status"""
    print(f"\n📊 Probando Status del job: {job_id}")
    
    try:
        response = requests.get(f"{BASE_URL}/status/{job_id}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error en status: {e}")
        return None

def test_result(job_id):
    """Prueba el endpoint de result"""
    print(f"\n📄 Probando Result del job: {job_id}")
    
    try:
        response = requests.get(f"{BASE_URL}/result/{job_id}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error en result: {e}")
        return None

def test_update_status(job_id):
    """Prueba el endpoint de update_status"""
    print(f"\n🔄 Probando Update Status del job: {job_id}")
    
    update_data = {
        "status": "completed",
        "result": {
            "text_extracted": "Texto de prueba extraído",
            "pages": 1,
            "processing_time": 2.5
        },
        "error": ""  # String vacío en lugar de null
    }
    
    try:
        response = requests.post(f"{BASE_URL}/update_status/{job_id}", json=update_data)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error en update_status: {e}")
        return False

def main():
    """Función principal de pruebas"""
    print("=" * 60)
    print("🧪 TESTEO COMPLETO DE LA API SIMPLE (PUERTO 8003)")
    print("=" * 60)
    
    # 1. Probar health check
    if not test_health():
        print("❌ API no está disponible. Asegúrate de que esté ejecutándose en puerto 8003")
        return
    
    # 2. Probar upload
    job_id = test_upload()
    if not job_id:
        print("❌ Upload falló")
        return
    
    print(f"✅ Job creado: {job_id}")
    
    # 3. Probar status inicial
    print("\n⏳ Esperando 2 segundos...")
    time.sleep(2)
    status_result = test_status(job_id)
    
    # 4. Probar update_status (simular que el worker completó)
    if test_update_status(job_id):
        print("✅ Update status funcionó")
        
        # 5. Probar status después del update
        print("\n⏳ Verificando status después del update...")
        time.sleep(1)
        test_status(job_id)
        
        # 6. Probar result
        print("\n⏳ Probando obtener resultado...")
        test_result(job_id)
    else:
        print("❌ Update status falló")
    
    print("\n" + "=" * 60)
    print("🏁 PRUEBAS COMPLETADAS")
    print("=" * 60)

if __name__ == "__main__":
    main()
