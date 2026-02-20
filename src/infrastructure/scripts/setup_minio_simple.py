#!/usr/bin/env python3
"""
Script simplificado de configuración inicial de MinIO para el sistema Tutor IA
Compatible con minio-py 7.2.16
"""

import json
import sys
from minio import Minio
from minio.error import S3Error
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de conexión
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_USER", "REDACTED")
MINIO_SECRET_KEY = os.getenv("MINIO_PASSWORD", "REDACTED")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Buckets y su configuración
BUCKETS_CONFIG = {
    "pdfs": "PDFs originales subidos por estudiantes",
    "processed": "PDFs procesados con OCR",
    "media": "Archivos multimedia (imágenes, audio)",
    "temp": "Archivos temporales",
    "backups": "Respaldos del sistema"
}

# Política de acceso público para lectura de media
MEDIA_BUCKET_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": "*"},
            "Action": ["s3:GetObject"],
            "Resource": ["arn:aws:s3:::media/*"]
        }
    ]
}


def create_minio_client():
    """Crear cliente de MinIO"""
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        print(f"✅ Conectado a MinIO en {MINIO_ENDPOINT}")
        return client
    except Exception as e:
        print(f"❌ Error conectando a MinIO: {e}")
        sys.exit(1)


def setup_buckets(client):
    """Configurar buckets"""
    print("\n📦 Configurando buckets...")
    
    for bucket_name, description in BUCKETS_CONFIG.items():
        print(f"\n   Bucket: {bucket_name}")
        print(f"   Descripción: {description}")
        
        try:
            if client.bucket_exists(bucket_name):
                print(f"   ✓ Bucket ya existe")
            else:
                client.make_bucket(bucket_name)
                print(f"   ✓ Bucket creado")
        except S3Error as e:
            print(f"   ❌ Error: {e}")
            continue
        
        # Configurar política pública para media
        if bucket_name == "media":
            try:
                policy_json = json.dumps(MEDIA_BUCKET_POLICY)
                client.set_bucket_policy(bucket_name, policy_json)
                print(f"   ✓ Política de acceso público configurada")
            except S3Error as e:
                print(f"   ⚠️  No se pudo configurar política: {e}")


def create_test_structure(client):
    """Crear estructura de carpetas de ejemplo"""
    print("\n📁 Creando estructura de carpetas de ejemplo...")
    
    test_folders = {
        "pdfs": ["2024/", "2025/"],
        "processed": ["ocr/", "analyzed/"],
        "media": ["images/", "audio/", "video/"],
        "temp": ["uploads/", "processing/"],
        "backups": ["daily/", "weekly/", "monthly/"]
    }
    
    for bucket, folders in test_folders.items():
        if not client.bucket_exists(bucket):
            continue
            
        for folder in folders:
            try:
                # Crear un archivo placeholder para crear la carpeta
                from io import BytesIO
                data = BytesIO(b"")
                client.put_object(
                    bucket,
                    f"{folder}.keep",
                    data=data,
                    length=0
                )
                print(f"   ✓ {bucket}/{folder}")
            except S3Error as e:
                print(f"   ⚠️  Error en {bucket}/{folder}: {e}")


def verify_setup(client):
    """Verificar que todo está configurado correctamente"""
    print("\n🔍 Verificando configuración...")
    
    all_good = True
    for bucket_name in BUCKETS_CONFIG.keys():
        try:
            if client.bucket_exists(bucket_name):
                # Contar objetos
                objects = list(client.list_objects(bucket_name))
                print(f"   ✓ {bucket_name}: OK ({len(objects)} objetos)")
            else:
                print(f"   ❌ {bucket_name}: NO EXISTE")
                all_good = False
        except S3Error as e:
            print(f"   ❌ {bucket_name}: ERROR - {e}")
            all_good = False
    
    return all_good


def main():
    """Función principal"""
    print("🚀 Iniciando configuración de MinIO para Tutor IA")
    print("=" * 50)
    
    # Crear cliente
    client = create_minio_client()
    
    # Configurar buckets
    setup_buckets(client)
    
    # Crear estructura de ejemplo
    create_test_structure(client)
    
    # Verificar configuración
    if verify_setup(client):
        print("\n✅ ¡Configuración completada exitosamente!")
    else:
        print("\n⚠️  Configuración completada con advertencias")
    
    print("\n📋 Resumen de buckets:")
    for bucket, description in BUCKETS_CONFIG.items():
        print(f"   • {bucket}: {description}")
    
    print("\n⚠️  Nota: Las políticas de lifecycle deben configurarse manualmente")
    print("   en la consola de MinIO (http://localhost:9001) debido a la")
    print("   versión de la librería minio-py instalada.")
    
    print("\n🎯 Próximos pasos:")
    print("   1. Implementar cliente MinIO en el servicio de procesamiento")
    print("   2. Configurar el API Gateway para manejar CORS")
    print("   3. Probar upload/download de archivos")


if __name__ == "__main__":
    main()