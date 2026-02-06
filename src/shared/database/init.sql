-- ==================================================================================
-- ARCHIVO MAESTRO DE INICIALIZACIÓN (TutorIA - B2C Engineering)
-- Versión: 5.0 (Optimized: Indexes, Constraints & Triggers)
-- ==================================================================================

-- 0. CONFIGURACIÓN DE SEGURIDAD
-- Uso de DO block para idempotencia (no falla si ya existe)
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'REDACTED') THEN

      CREATE ROLE REDACTED LOGIN PASSWORD 'REDACTED';
      GRANT ALL PRIVILEGES ON DATABASE tutor_ia_db TO REDACTED;
      ALTER USER REDACTED CREATEDB; 
   END IF;
END
$do$;

-- Habilitar extensión para UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Función automática para actualizar el campo 'updated_at'
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 1. ENUMS
-- Usamos IF NOT EXISTS para evitar errores en re-despliegues limpios
DROP TYPE IF EXISTS cognitive_type_enum CASCADE;
CREATE TYPE cognitive_type_enum AS ENUM ('procedural', 'declarative', 'interpretative', 'conceptual');

DROP TYPE IF EXISTS domain_field_enum CASCADE;
CREATE TYPE domain_field_enum AS ENUM ('mathematics', 'physics', 'computer_science', 'electronics', 'chemistry', 'general_engineering', 'other');

DROP TYPE IF EXISTS file_status_enum CASCADE;
CREATE TYPE file_status_enum AS ENUM ('uploading', 'processing', 'ready', 'error');

-- ==================================================================================
-- 1.5. USUARIOS DE SISTEMA (Auth Service)
-- ==================================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trigger para users
DROP TRIGGER IF EXISTS update_users_modtime ON users;
CREATE TRIGGER update_users_modtime BEFORE UPDATE ON users FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

GRANT ALL PRIVILEGES ON TABLE users TO REDACTED;

-- 2. PERFIL DE ESTUDIANTE (Learning Service)
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    auth_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, 
    email VARCHAR(255) NOT NULL,
    university_name VARCHAR(200),
    degree_name VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- MEJORA: Un usuario solo puede tener un perfil de estudiante
    CONSTRAINT uq_students_auth_user_id UNIQUE (auth_user_id)
);

-- MEJORA: Índice para búsquedas rápidas por user_id (Joins de Auth)
CREATE INDEX IF NOT EXISTS idx_students_auth_user_id ON students(auth_user_id);

GRANT ALL PRIVILEGES ON TABLE students TO REDACTED;

-- 3. ASIGNATURAS PERSONALES
CREATE TABLE IF NOT EXISTS courses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    domain_field domain_field_enum DEFAULT 'general_engineering',
    cognitive_type cognitive_type_enum DEFAULT 'procedural',
    semester INTEGER,
    color_theme VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- MEJORA: Evitar que un alumno tenga dos cursos con el mismo nombre exacto
    CONSTRAINT uq_courses_student_name UNIQUE (student_id, name)
);

-- MEJORA: Índice para listar cursos de un alumno rápidamente
CREATE INDEX IF NOT EXISTS idx_courses_student_id ON courses(student_id);

GRANT ALL PRIVILEGES ON TABLE courses TO REDACTED;

-- 4. CONTENIDO / APUNTES
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID REFERENCES courses(id) ON DELETE SET NULL, 
    student_id UUID REFERENCES students(id), -- Backup de propiedad
    
    filename VARCHAR(255) NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    status file_status_enum DEFAULT 'uploading',
    
    page_count INTEGER,
    processed_latex_content TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trigger para documents
DROP TRIGGER IF EXISTS update_documents_modtime ON documents;
CREATE TRIGGER update_documents_modtime BEFORE UPDATE ON documents FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

-- MEJORA: Índices para búsquedas
CREATE INDEX IF NOT EXISTS idx_documents_course_id ON documents(course_id);
CREATE INDEX IF NOT EXISTS idx_documents_student_id ON documents(student_id);

GRANT ALL PRIVILEGES ON TABLE documents TO REDACTED;

-- 5. EXÁMENES GENERADOS
CREATE TABLE IF NOT EXISTS generated_exams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID REFERENCES courses(id) ON DELETE SET NULL,
    student_id UUID REFERENCES students(id),
    
    title VARCHAR(200),
    -- MEJORA: DECIMAL(5, 2) permite guardar 100.00 (antes max era 99.99)
    score DECIMAL(5, 2), 
    status VARCHAR(50) DEFAULT 'processing',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_exams_course_id ON generated_exams(course_id);
CREATE INDEX IF NOT EXISTS idx_generated_exams_student_id ON generated_exams(student_id);

GRANT ALL PRIVILEGES ON TABLE generated_exams TO REDACTED;

CREATE TABLE IF NOT EXISTS exam_questions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exam_id UUID NOT NULL REFERENCES generated_exams(id) ON DELETE CASCADE,
    
    question_latex TEXT NOT NULL,
    solution_latex TEXT NOT NULL,
    explanation TEXT,
    
    source_document_id UUID REFERENCES documents(id),
    order_index INTEGER
);

-- MEJORA: Índice crítico para cargar un examen (busca todas las preguntas por exam_id)
CREATE INDEX IF NOT EXISTS idx_exam_questions_exam_id ON exam_questions(exam_id);

GRANT ALL PRIVILEGES ON TABLE exam_questions TO REDACTED;

-- Permisos finales generales (asegura acceso a futuras tablas en public)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO REDACTED;