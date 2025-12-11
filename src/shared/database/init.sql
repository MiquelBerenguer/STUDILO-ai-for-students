-- ==================================================================================
-- ARCHIVO MAESTRO DE INICIALIZACIÓN (TutorIA - B2C Engineering)
-- Versión: 4.0 (Usuario Soberano + Inteligencia STEM)
-- ==================================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. ENUMS (El "Cerebro" de la IA)
-- Aunque sea B2C, necesitamos saber QUÉ es la asignatura para razonar bien.
DROP TYPE IF EXISTS cognitive_type_enum CASCADE;
CREATE TYPE cognitive_type_enum AS ENUM ('procedural', 'declarative', 'interpretative', 'conceptual');

DROP TYPE IF EXISTS domain_field_enum CASCADE;
CREATE TYPE domain_field_enum AS ENUM ('mathematics', 'physics', 'computer_science', 'electronics', 'chemistry', 'general_engineering', 'other');

DROP TYPE IF EXISTS file_status_enum CASCADE;
CREATE TYPE file_status_enum AS ENUM ('uploading', 'processing', 'ready', 'error');

-- 2. USUARIOS (El Cliente)
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    auth_user_id VARCHAR(255) UNIQUE NOT NULL, -- Link con Auth Service
    email VARCHAR(255) UNIQUE NOT NULL,
    university_name VARCHAR(200), -- Dato informativo (no restrictivo)
    degree_name VARCHAR(200),     -- Dato informativo
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. ASIGNATURAS PERSONALES (User-Centric)
-- Cada alumno crea SUS asignaturas. Si hay 1000 alumnos de Cálculo, habrá 1000 registros aquí.
CREATE TABLE IF NOT EXISTS courses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    
    name VARCHAR(200) NOT NULL, -- Ej: "Mis Mates II"
    
    -- METADATOS CRÍTICOS (Para que la IA sepa comportarse)
    -- El usuario puede seleccionarlos o la IA inferirlos
    domain_field domain_field_enum DEFAULT 'general_engineering',
    cognitive_type cognitive_type_enum DEFAULT 'procedural',
    
    semester INTEGER,
    color_theme VARCHAR(50), -- Para el frontend
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. CONTENIDO / APUNTES (Ingesta)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    
    filename VARCHAR(255) NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    status file_status_enum DEFAULT 'uploading',
    
    -- Resultados de la Ingesta (Worker Visión)
    page_count INTEGER,
    processed_latex_content TEXT, -- Aquí vive el resultado de la IA Visión
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. EXÁMENES GENERADOS
CREATE TABLE IF NOT EXISTS generated_exams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    
    title VARCHAR(200),
    score DECIMAL(4, 2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exam_questions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exam_id UUID NOT NULL REFERENCES generated_exams(id) ON DELETE CASCADE,
    
    question_latex TEXT NOT NULL,
    solution_latex TEXT NOT NULL,
    explanation TEXT,
    
    -- Referencia al documento original del usuario (RAG)
    source_document_id UUID REFERENCES documents(id),
    
    order_index INTEGER
);