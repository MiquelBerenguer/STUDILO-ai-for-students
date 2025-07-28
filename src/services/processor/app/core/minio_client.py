from minio import Minio
from minio.error import S3Error
import io
from typing import Optional, BinaryIO
import structlog
from datetime import timedelta
from ..config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class MinIOClient:
    def __init__(self):
        self.client: Optional[Minio] = None
        self.bucket_name = settings.minio_bucket
        
    async def connect(self):
        """Inicializar conexión a MinIO"""
        try:
            self.client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            
            # Crear bucket si no existe
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
            
            logger.info("MinIO connection successful")
        except Exception as e:
            logger.error("MinIO connection failed", error=str(e))
            raise
    
    async def upload_file(self, file_name: str, file_data: BinaryIO, content_type: str = "application/octet-stream") -> str:
        """Subir archivo a MinIO"""
        try:
            # Obtener tamaño del archivo
            file_data.seek(0, 2)  # Ir al final
            file_size = file_data.tell()
            file_data.seek(0)  # Volver al inicio
            
            # Subir archivo
            result = self.client.put_object(
                self.bucket_name,
                file_name,
                file_data,
                file_size,
                content_type=content_type
            )
            
            logger.info("File uploaded successfully", 
                       file_name=file_name, 
                       size=file_size,
                       etag=result.etag)
            
            return result.etag
        except S3Error as e:
            logger.error("MinIO upload error", error=str(e))
            raise
    
    async def download_file(self, file_name: str) -> bytes:
        """Descargar archivo de MinIO"""
        try:
            response = self.client.get_object(self.bucket_name, file_name)
            data = response.read()
            response.close()
            response.release_conn()
            
            logger.info("File downloaded successfully", file_name=file_name)
            return data
        except S3Error as e:
            logger.error("MinIO download error", error=str(e))
            raise
    
    async def delete_file(self, file_name: str) -> bool:
        """Eliminar archivo de MinIO"""
        try:
            self.client.remove_object(self.bucket_name, file_name)
            logger.info("File deleted successfully", file_name=file_name)
            return True
        except S3Error as e:
            logger.error("MinIO delete error", error=str(e))
            return False
    
    async def file_exists(self, file_name: str) -> bool:
        """Verificar si existe un archivo"""
        try:
            self.client.stat_object(self.bucket_name, file_name)
            return True
        except S3Error:
            return False
    
    async def generate_presigned_url(self, file_name: str, expires: int = 3600) -> str:
        """Generar URL temporal para descarga"""
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                file_name,
                expires=timedelta(seconds=expires)
            )
            return url
        except S3Error as e:
            logger.error("MinIO presigned URL error", error=str(e))
            raise
    
    async def list_files(self, prefix: str = "", limit: int = 1000) -> list:
        """Listar archivos en el bucket"""
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            
            files = []
            for obj in objects:
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag
                })
                if len(files) >= limit:
                    break
                    
            return files
        except S3Error as e:
            logger.error("MinIO list error", error=str(e))
            return []

# Instancia global
minio_client = MinIOClient()