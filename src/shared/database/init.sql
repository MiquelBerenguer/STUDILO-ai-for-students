-- ==================================================================================
-- ARCHIVO MAESTRO DE INICIALIZACIÓN DE BASE DE DATOS (TutorIA)
-- Versión: 2.0 (Corregida con Tipos Cognitivos de Negocio)
-- ==================================================================================

-- 1. EXTENSIONES BÁSICAS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. DEFINICIÓN DE TIPOS (ENUMS) - El "ADN" del sistema
-- IMPORTANTE: Aquí definimos los 4 tipos de inteligencia según el negocio.
DROP TYPE IF EXISTS cognitive_type_enum CASCADE;
CREATE TYPE cognitive_type_enum AS ENUM ('procedural', 'declarative', 'interpretative', 'conceptual');

DROP TYPE IF EXISTS pattern_scope_enum CASCADE;
CREATE TYPE pattern_scope_enum AS ENUM ('global', 'domain', 'course');

DROP TYPE IF EXISTS exam_difficulty_enum CASCADE;
CREATE TYPE exam_difficulty_enum AS ENUM ('easy', 'medium', 'hard');

-- 3. USUARIOS Y JERARQUÍA ACADÉMICA
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    auth_user_id VARCHAR(255) UNIQUE NOT NULL, -- ID que vendrá del Auth Service (Firebase/Cognito/Propio)
    first_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    
    name VARCHAR(200) NOT NULL,
    
    -- AQUÍ ESTÁ EL CAMBIO CLAVE: El curso define cómo "piensa" la IA.
    -- Ej: "Cálculo" -> 'procedural', "Historia" -> 'declarative'
    cognitive_type cognitive_type_enum NOT NULL DEFAULT 'declarative',
    
    academic_level VARCHAR(50) NOT NULL, 
    field_of_study VARCHAR(100),          
    description TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. GESTIÓN DE TEMAS (Normalización para "Soberanía del Dato")
CREATE TABLE IF NOT EXISTS topics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL, -- Ej: "Derivadas", "Revolución Francesa"
    
    base_difficulty DECIMAL(3, 1) DEFAULT 5.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(course_id, name) -- Evita duplicados dentro de un mismo curso
);
-- Índice para búsquedas rápidas por curso
CREATE INDEX idx_topics_course ON topics(course_id);

-- 5. MATERIALES Y APUNTES
CREATE TABLE IF NOT EXISTS course_materials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    
    filename VARCHAR(255) NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    file_type VARCHAR(10),
    is_private BOOLEAN DEFAULT TRUE,
    
    -- Metadata IA
    ai_difficulty_score DECIMAL(3, 1) DEFAULT 5.0,
    estimated_study_minutes INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla Pivote: Un PDF puede hablar de muchos temas
CREATE TABLE IF NOT EXISTS material_topics (
    material_id UUID NOT NULL REFERENCES course_materials(id) ON DELETE CASCADE,
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    relevance_score DECIMAL(3,2) DEFAULT 1.0, 
    PRIMARY KEY (material_id, topic_id)
);

-- 6. INFRAESTRUCTURA DE INTELIGENCIA (Patrones Pedagógicos)
CREATE TABLE IF NOT EXISTS pedagogical_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    scope pattern_scope_enum NOT NULL, -- Global, Domain, o Course
    target_id VARCHAR(255), -- ID del curso o nombre del dominio (ej. "engineering")
    
    cognitive_type cognitive_type_enum NOT NULL, -- Ahora usa los 4 tipos correctos
    difficulty exam_difficulty_enum NOT NULL,
    
    reasoning_recipe TEXT NOT NULL, -- El "System Prompt" del profesor
    original_question TEXT, -- Ejemplo Few-Shot
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
-- Índice compuesto para búsquedas ultra-rápidas del StyleSelector
CREATE INDEX idx_patterns_lookup ON pedagogical_patterns(scope, target_id, cognitive_type, difficulty);

-- 7. MEMORIA DE PROGRESO (Mastery)
CREATE TABLE IF NOT EXISTS topic_mastery (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    
    mastery_level INTEGER DEFAULT 0, -- 0 a 100
    consecutive_failures INTEGER DEFAULT 0,
    last_reviewed_at TIMESTAMP WITH TIME ZONE,
    
    UNIQUE(student_id, topic_id)
);

-- 8. EXÁMENES Y PREGUNTAS
CREATE TABLE IF NOT EXISTS exams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    
    title VARCHAR(200),
    scope_type VARCHAR(20) DEFAULT 'SPECIFIC_TOPICS',
    
    -- Lista de IDs de temas incluidos (Formato JSONB para flexibilidad)
    topics_included JSONB, 
    
    status VARCHAR(20) DEFAULT 'DRAFT', 
    score_average DECIMAL(4, 2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_exams_topics ON exams USING GIN (topics_included);

CREATE TABLE IF NOT EXISTS exam_questions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exam_id UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    
    question_text TEXT NOT NULL,
    options JSONB, -- Array de opciones si es test
    correct_answer TEXT,
    explanation TEXT,
    
    -- Rastro de Auditoría IA (Trazabilidad)
    source_chunk_id VARCHAR(255),
    used_pattern_id UUID REFERENCES pedagogical_patterns(id),
    
    score DECIMAL(4, 2),
    feedback TEXT,
    order_index INTEGER
);

-- 9. PLANIFICADOR DE ESTUDIO (Estructura Limpia)
CREATE TABLE IF NOT EXISTS study_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    
    name VARCHAR(200) DEFAULT 'Plan Global Actual',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    
    configuration JSONB DEFAULT '{}', -- Preferencias del usuario
    status VARCHAR(20) DEFAULT 'ACTIVE',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Relación Many-to-Many entre Plan y Exámenes
CREATE TABLE IF NOT EXISTS study_plan_items (
    study_plan_id UUID NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
    exam_id UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    priority_override INTEGER DEFAULT 1,
    PRIMARY KEY (study_plan_id, exam_id)
);

-- Sesiones de calendario concretas
CREATE TABLE IF NOT EXISTS study_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_id UUID NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
    
    exam_id UUID NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    topic_id UUID REFERENCES topics(id), -- Foco opcional de la sesión
    
    scheduled_date DATE NOT NULL,
    duration_minutes INTEGER NOT NULL,
    is_completed BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);