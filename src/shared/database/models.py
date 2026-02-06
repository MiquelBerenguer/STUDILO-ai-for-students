import uuid
import enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB  # Tipos nativos de Postgres
from src.shared.database.database import Base

# =============================================================================
# 1. ENUMS (Para consistencia con la DB)
# =============================================================================
class ExamStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class CognitiveType(str, enum.Enum):
    PROCEDURAL = "procedural"
    DECLARATIVE = "declarative"
    INTERPRETATIVE = "interpretative"
    CONCEPTUAL = "conceptual"

# =============================================================================
# 2. MODELOS DE USUARIO Y PERFIL
# =============================================================================

class User(Base):
    __tablename__ = "users"

    # UUID nativo como Primary Key (Best Practice)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relación 1-1 con Student
    student_profile = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Student(Base):
    __tablename__ = "students"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Vinculación fuerte con la tabla de autenticación
    auth_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    email = Column(String, nullable=False)
    university_name = Column(String, nullable=True)
    degree_name = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    user = relationship("User", back_populates="student_profile")
    courses = relationship("Course", back_populates="student", cascade="all, delete-orphan")
    # exams = relationship("GeneratedExam", back_populates="student") # Descomentar si añadimos relación directa

# =============================================================================
# 3. MODELOS DE APRENDIZAJE (CURSOS Y CONTENIDO)
# =============================================================================

class Course(Base):
    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String, nullable=False)
    
    # Metadatos del curso
    domain_field = Column(String, default='general_engineering')
    cognitive_type = Column(String, default='procedural') # Guardamos el enum como string
    
    semester = Column(Integer, nullable=True)
    color_theme = Column(String, default="#3498db")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    student = relationship("Student", back_populates="courses")
    exams = relationship("GeneratedExam", back_populates="course", cascade="all, delete-orphan")
    # documents = relationship("Document", back_populates="course") # Futuro: Documentos

# =============================================================================
# 4. MODELOS DE EXÁMENES (GENERACIÓN)
# =============================================================================

class GeneratedExam(Base):
    """
    Representa un examen generado por la IA.
    Sustituye a la antigua clase 'Exam' pero es más completa.
    """
    __tablename__ = "generated_exams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    
    title = Column(String, nullable=False)
    status = Column(String, default=ExamStatus.PROCESSING.value) # queued, processing, completed
    
    # Puntuación global del examen (0-100)
    score = Column(Numeric(5, 2), nullable=True) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    course = relationship("Course", back_populates="exams")
    questions = relationship("ExamQuestion", back_populates="exam", cascade="all, delete-orphan")

class ExamQuestion(Base):
    """
    Cada pregunta individual dentro de un examen generado.
    """
    __tablename__ = "exam_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("generated_exams.id", ondelete="CASCADE"), nullable=False)
    
    # Contenido generado (LaTeX)
    question_latex = Column(Text, nullable=False)
    solution_latex = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    
    order_index = Column(Integer, default=0)

    # Relaciones
    exam = relationship("GeneratedExam", back_populates="questions")