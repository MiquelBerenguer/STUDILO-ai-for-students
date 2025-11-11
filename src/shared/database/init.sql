-- Asegurarnos de que la extensión para UUIDs esté disponible
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tabla de Usuarios (Se creará en la base de datos 'tutor_ia_db' automáticamente si configuramos bien el paso 2)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para búsquedas rápidas por email (vital para el login)
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);