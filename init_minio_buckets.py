#!/usr/bin/env python3
"""
Script para inicializar buckets en MinIO
Ejecutar después de que MinIO esté levantado
"""

import os
import sys
from minio import Minio
from minio.error import S3Error
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_buckets():
    """Crea los buckets necesarios en MinIO"""
    
    # Configuración de MinIO
    MINIO_ENDPOINT = 'localhost:9000'
    MINIO_ACCESS_KEY = 'REDACTED'
    MINIO_SECRET_KEY = 'REDACTED'
    
    logger.info(f"🔗 Conectando a MinIO en {MINIO_ENDPOINT}")
    
    try:
        # Crear cliente MinIO
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False  # No usar HTTPS en desarrollo
        )
        
        # Definir buckets a crear - NOTA: ya tienes 'documents' con 'uploads' dentro
        buckets_to_create = [
            {
                'name': 'uploads',
                'description': 'Archivos PDF originales subidos por usuarios'
            },
            {
                'name': 'processed',
                'description': 'Archivos procesados y resultados de OCR'
            },
            {
                'name': 'temp',
                'description': 'Archivos temporales durante procesamiento'
            }
        ]
        
        # Verificar si ya existe 'documents' y listar su contenido
        if client.bucket_exists('documents'):
            logger.info("📦 Bucket 'documents' ya existe")
            objects = client.list_objects('documents', recursive=True)
            logger.info("   Contenido actual:")
            for obj in objects:
                logger.info(f"     - {obj.object_name}")
        
        # Crear cada bucket nuevo
        for bucket_info in buckets_to_create:
            bucket_name = bucket_info['name']
            
            if client.bucket_exists(bucket_name):
                logger.info(f"✅ Bucket '{bucket_name}' ya existe")
            else:
                client.make_bucket(bucket_name)
                logger.info(f"✨ Bucket '{bucket_name}' creado exitosamente")
                logger.info(f"   📝 {bucket_info['description']}")
        
        # Listar todos los buckets para verificar
        logger.info("\n📦 Todos los buckets disponibles en MinIO:")
        buckets_list = client.list_buckets()
        for bucket in buckets_list:
            logger.info(f"   - {bucket.name} (creado: {bucket.creation_date})")
        
        logger.info("\n✅ Inicialización de MinIO completada exitosamente")
        return True
        
    except S3Error as e:
        logger.error(f"❌ Error S3: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")
        return False

def test_upload():
    """Prueba subiendo un archivo de test"""
    
    MINIO_ENDPOINT = 'localhost:9000'
    MINIO_ACCESS_KEY = 'REDACTED'
    MINIO_SECRET_KEY = 'REDACTED'
    
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False
        )
        
        # Crear archivo de prueba
        import tempfile
        import datetime
        
        test_content = f"Este es un archivo de prueba para MinIO - {datetime.datetime.now()}"
        
        # Usar archivo temporal
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_content)
            temp_file = f.name
        
        # Subir archivo al bucket 'uploads'
        object_name = f"test/test_file_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        client.fput_object(
            'uploads',
            object_name,
            temp_file
        )
        
        logger.info(f"📤 Archivo de prueba subido exitosamente a uploads/{object_name}")
        
        # Verificar que se puede leer
        response = client.get_object('uploads', object_name)
        data = response.read().decode('utf-8')
        logger.info(f"📥 Archivo leído correctamente: {data[:50]}...")
        response.close()
        response.release_conn()
        
        # Limpiar archivo temporal
        os.remove(temp_file)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en prueba de upload: {e}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Iniciando configuración de MinIO...")
    logger.info("=" * 60)
    
    # Crear buckets
    if create_buckets():
        # Realizar prueba de upload
        logger.info("\n🧪 Ejecutando prueba de upload...")
        logger.info("-" * 60)
        if test_upload():
            logger.info("\n" + "=" * 60)
            logger.info("✅ MinIO está listo para usar!")
            logger.info("=" * 60)
            sys.exit(0)
        else:
            logger.error("\n⚠️ Buckets creados pero prueba de upload falló")
            sys.exit(1)
    else:
        logger.error("\n❌ No se pudieron crear los buckets")
        sys.exit(1)