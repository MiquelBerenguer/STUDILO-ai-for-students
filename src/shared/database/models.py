import uuid
import enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB  # Tipos nativos de Postgres
from src.shared.database.database import Base

# Definimos el Enum para garantizar integridad en el estado del proceso
class ExamStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"

    # CAMBIO 1: UUID como Primary Key
    # Ventaja: Previene ataques de enumeración y facilita el Sharding [cite: 209, 213]
    # Usamos el tipo nativo UUID de Postgres (128 bits) en lugar de String (más pesado)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relación
    exams = relationship("Exam", back_populates="student", cascade="all, delete-orphan")

class Exam(Base):
    __tablename__ = "exams"

    # Coincide con el task_id generado en el API Gateway (UUID v4) [cite: 208]
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Key debe coincidir en tipo con User.id
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    topic = Column(String, nullable=False)
    difficulty = Column(String, nullable=False) # Podría ser otro Enum si hay dificultades fijas
    
    # CAMBIO 2: Enum para Estado
    # Evita errores de tipografía y hace el código más robusto.
    status = Column(String, default=ExamStatus.QUEUED.value, index=True)
    
    # CAMBIO 3: JSONB para datos semi-estructurados 
    # Aquí guardamos la estructura del examen (preguntas, opciones) antes de generar el PDF.
    # JSONB permite consultas rápidas dentro del objeto JSON si fuera necesario.
    content = Column(JSONB, nullable=True) 
    
    # URL final del PDF (S3)
    result_url = Column(String, nullable=True)
    
    # Mensaje de error si status == 'failed'
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True) # Indexado para ordenar por fecha
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    student = relationship("User", back_populates="exams")