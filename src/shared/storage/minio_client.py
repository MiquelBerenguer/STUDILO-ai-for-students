"""
Cliente MinIO para el sistema Tutor IA
Proporciona funciones para subir, descargar y gestionar archivos
"""

import os
import logging
from datetime import timedelta
from typing import Optional, BinaryIO, Tuple
from minio import Minio
from minio.error import S3Error
from io import BytesIO
import hashlib

logger = logging.getLogger(__name__)


class MinIOClient:
    """Cliente para interactuar con MinIO"""
    
    def __init__(
        self,
        endpoint: str = None,
        access_key: str = None,
        secret_key: str = None,
        secure: bool = False
    ):
        """
        Inicializar cliente MinIO
        
        Args:
            endpoint: URL del servidor MinIO (ej: "localhost:9000")
            access_key: Access key de MinIO
            secret_key: Secret key de MinIO
            secure: Usar HTTPS
        """
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "REDACTED")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "REDACTED")
        self.secure = secure
        
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )
        
        logger.info(f"Cliente MinIO inicializado para {self.endpoint}")
    
    def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        file_data: BinaryIO,
        file_size: int,
        content_type: str = "application/octet-stream",
        metadata: dict = None
    ) -> Tuple[bool, str]:
        """
        Subir archivo a MinIO
        
        Args:
            bucket_name: Nombre del bucket
            object_name: Nombre del objeto en MinIO
            file_data: Datos del archivo (file-like object)
            file_size: Tamaño del archivo en bytes
            content_type: Tipo MIME del archivo
            metadata: Metadatos adicionales
            
        Returns:
            Tuple (success, message/etag)
        """
        try:
            # Agregar metadatos por defecto
            if metadata is None:
                metadata = {}
            
            # Calcular hash MD5 para verificación
            file_data.seek(0)
            md5_hash = hashlib.md5(file_data.read()).hexdigest()
            file_data.seek(0)
            
            metadata['md5'] = md5_hash
            
            # Subir archivo
            result = self.client.put_object(
                bucket_name,
                object_name,
                file_data,
                file_size,
                content_type=content_type,
                metadata=metadata
            )
            
            logger.info(f"Archivo subido: {bucket_name}/{object_name} (etag: {result.etag})")
            return True, result.etag
            
        except S3Error as e:
            logger.error(f"Error S3 al subir archivo: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error inesperado al subir archivo: {e}")
            return False, str(e)
    
    def download_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: Optional[str] = None
    ) -> Tuple[bool, any]:
        """
        Descargar archivo de MinIO
        
        Args:
            bucket_name: Nombre del bucket
            object_name: Nombre del objeto
            file_path: Ruta donde guardar el archivo (opcional)
            
        Returns:
            Tuple (success, file_path o BytesIO)
        """
        try:
            # Obtener objeto
            response = self.client.get_object(bucket_name, object_name)
            
            if file_path:
                # Guardar en archivo
                with open(file_path, 'wb') as file:
                    for data in response.stream(32*1024):
                        file.write(data)
                response.close()
                response.release_conn()
                
                logger.info(f"Archivo descargado: {bucket_name}/{object_name} -> {file_path}")
                return True, file_path
            else:
                # Retornar como BytesIO
                data = BytesIO(response.read())
                response.close()
                response.release_conn()
                
                logger.info(f"Archivo descargado en memoria: {bucket_name}/{object_name}")
                return True, data
                
        except S3Error as e:
            logger.error(f"Error S3 al descargar archivo: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error inesperado al descargar archivo: {e}")
            return False, str(e)
    
    def delete_file(self, bucket_name: str, object_name: str) -> Tuple[bool, str]:
        """
        Eliminar archivo de MinIO
        
        Args:
            bucket_name: Nombre del bucket
            object_name: Nombre del objeto
            
        Returns:
            Tuple (success, message)
        """
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"Archivo eliminado: {bucket_name}/{object_name}")
            return True, "Archivo eliminado exitosamente"
        except S3Error as e:
            logger.error(f"Error S3 al eliminar archivo: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error inesperado al eliminar archivo: {e}")
            return False, str(e)
    
    def get_presigned_url(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> Tuple[bool, str]:
        """
        Generar URL pre-firmada para acceso temporal
        
        Args:
            bucket_name: Nombre del bucket
            object_name: Nombre del objeto
            expires: Tiempo de expiración
            
        Returns:
            Tuple (success, url o error)
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name,
                object_name,
                expires=expires
            )
            logger.info(f"URL pre-firmada generada para: {bucket_name}/{object_name}")
            return True, url
        except S3Error as e:
            logger.error(f"Error S3 al generar URL: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error inesperado al generar URL: {e}")
            return False, str(e)
    
    def list_files(
        self,
        bucket_name: str,
        prefix: str = "",
        recursive: bool = True
    ) -> Tuple[bool, list]:
        """
        Listar archivos en un bucket
        
        Args:
            bucket_name: Nombre del bucket
            prefix: Prefijo para filtrar
            recursive: Buscar recursivamente
            
        Returns:
            Tuple (success, list of objects o error)
        """
        try:
            objects = self.client.list_objects(
                bucket_name,
                prefix=prefix,
                recursive=recursive
            )
            
            file_list = []
            for obj in objects:
                file_list.append({
                    'name': obj.object_name,
                    'size': obj.size,
                    'last_modified': obj.last_modified,
                    'etag': obj.etag
                })
            
            logger.info(f"Listados {len(file_list)} archivos en {bucket_name}/{prefix}")
            return True, file_list
            
        except S3Error as e:
            logger.error(f"Error S3 al listar archivos: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error inesperado al listar archivos: {e}")
            return False, str(e)
    
    def move_file(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str
    ) -> Tuple[bool, str]:
        """
        Mover archivo entre buckets
        
        Args:
            source_bucket: Bucket origen
            source_object: Objeto origen
            dest_bucket: Bucket destino
            dest_object: Objeto destino
            
        Returns:
            Tuple (success, message)
        """
        try:
            # Copiar objeto
            self.client.copy_object(
                dest_bucket,
                dest_object,
                f"/{source_bucket}/{source_object}"
            )
            
            # Eliminar original
            self.client.remove_object(source_bucket, source_object)
            
            logger.info(f"Archivo movido: {source_bucket}/{source_object} -> {dest_bucket}/{dest_object}")
            return True, "Archivo movido exitosamente"
            
        except S3Error as e:
            logger.error(f"Error S3 al mover archivo: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error inesperado al mover archivo: {e}")
            return False, str(e)
    
    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """
        Verificar si un archivo existe
        
        Args:
            bucket_name: Nombre del bucket
            object_name: Nombre del objeto
            
        Returns:
            True si existe, False si no
        """
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error:
            return False


# Ejemplo de uso
if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Crear cliente
    minio_client = MinIOClient()
    
    # Ejemplo: Subir un archivo de prueba
    test_content = b"Este es un archivo de prueba para el sistema Tutor IA"
    test_file = BytesIO(test_content)
    
    success, result = minio_client.upload_file(
        bucket_name="temp",
        object_name="test/ejemplo.txt",
        file_data=test_file,
        file_size=len(test_content),
        content_type="text/plain",
        metadata={"uploaded_by": "test_script"}
    )
    
    if success:
        print(f"✅ Archivo subido exitosamente: {result}")
        
        # Generar URL temporal
        success, url = minio_client.get_presigned_url("temp", "test/ejemplo.txt")
        if success:
            print(f"📎 URL temporal: {url}")
    else:
        print(f"❌ Error: {result}")