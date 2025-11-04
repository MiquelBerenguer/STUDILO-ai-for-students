"""
Cliente MinIO para gestión de almacenamiento de archivos
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import io
from minio import Minio
from minio.error import S3Error
from app.config import get_settings

logger = logging.getLogger(__name__)

class MinIOClient:
    """Cliente para interactuar con MinIO/S3"""
    
    def __init__(self):
        """Inicializa el cliente MinIO"""
        settings = get_settings()
        
        # Usar settings con las credenciales correctas
        self.endpoint = settings.minio_endpoint
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key
        
        logger.info(f"🔗 Conectando a MinIO en {self.endpoint}")
        
        try:
            # Crear cliente
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=False  # No usar HTTPS en desarrollo
            )
            
            # Verificar conexión y crear buckets si no existen
            self._ensure_buckets()
            
            logger.info("✅ Cliente MinIO inicializado correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando MinIO: {e}")
            # No lanzar excepción para que el servicio pueda continuar
            self.client = None
    
    def _ensure_buckets(self):
        """Asegura que los buckets necesarios existan"""
        required_buckets = ['uploads', 'processed', 'temp']
        
        for bucket in required_buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info(f"✨ Bucket '{bucket}' creado")
                else:
                    logger.debug(f"✅ Bucket '{bucket}' ya existe")
            except S3Error as e:
                logger.warning(f"⚠️ Error verificando bucket '{bucket}': {e}")
                # Continuar sin fallar
    
    def upload_file(
        self, 
        file_data: bytes, 
        object_name: str, 
        bucket_name: str = 'uploads',
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Sube un archivo a MinIO
        """
        try:
            # Convertir bytes a stream
            file_stream = io.BytesIO(file_data)
            file_size = len(file_data)
            
            logger.info(f"📤 Subiendo archivo a {bucket_name}/{object_name}")
            
            # Subir archivo SIN metadata para evitar problemas de firma
            result = self.client.put_object(
                bucket_name,
                object_name,
                file_stream,
                file_size
            )
            
            logger.info(f"✅ Archivo subido exitosamente: {result.object_name}")
            
            return {
                'bucket': bucket_name,
                'object_name': object_name,
                'etag': result.etag,
                'version_id': result.version_id,
                'size': file_size
            }
            
        except S3Error as e:
            logger.error(f"❌ Error S3 subiendo archivo: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado subiendo archivo: {e}")
            raise
    
    def download_file(self, object_name: str, bucket_name: str = 'uploads') -> bytes:
        """
        Descarga un archivo de MinIO
        """
        try:
            logger.info(f"📥 Descargando {bucket_name}/{object_name}")
            
            # Obtener objeto
            response = self.client.get_object(bucket_name, object_name)
            
            # Leer contenido
            file_data = response.read()
            
            # Cerrar conexión
            response.close()
            response.release_conn()
            
            logger.info(f"✅ Archivo descargado: {len(file_data)} bytes")
            
            return file_data
            
        except S3Error as e:
            logger.error(f"❌ Error S3 descargando archivo: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado descargando archivo: {e}")
            raise
    
    def get_file_info(self, object_name: str, bucket_name: str = 'uploads') -> Optional[Dict[str, Any]]:
        """
        Obtiene información sobre un archivo
        """
        try:
            stat = self.client.stat_object(bucket_name, object_name)
            
            return {
                'object_name': stat.object_name,
                'size': stat.size,
                'etag': stat.etag,
                'content_type': stat.content_type,
                'last_modified': stat.last_modified.isoformat() if stat.last_modified else None
            }
            
        except S3Error as e:
            if e.code == 'NoSuchKey':
                logger.warning(f"⚠️ Archivo no encontrado: {bucket_name}/{object_name}")
                return None
            logger.error(f"❌ Error S3 obteniendo info: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado obteniendo info: {e}")
            return None

# Singleton para reutilizar la conexión
_minio_client = None

def get_minio_client() -> MinIOClient:
    """Obtiene la instancia singleton del cliente MinIO"""
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient()
    return _minio_client