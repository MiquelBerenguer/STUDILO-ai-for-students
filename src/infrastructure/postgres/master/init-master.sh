#!/bin/sh
set -e

# Función para logging
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "Iniciando configuración del PostgreSQL Master..."

# --- INICIO DE CAMBIOS ---
# Usar el script de shell para pasar variables de entorno a psql
# Esto nos permite parametrizar TODAS las credenciales.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL

    -- Crear usuario de replicación (leyendo de variables de entorno)
    CREATE USER ${POSTGRES_REPL_USER} WITH REPLICATION ENCRYPTED PASSWORD '${POSTGRES_REPL_PASSWORD}';
    
    -- Crear slot de replicación
    SELECT * FROM pg_create_physical_replication_slot('replica_1_slot');
    
    -- Crear base de datos para la aplicación (si no existe ya)
    SELECT 'CREATE DATABASE tutor_ia_db'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'tutor_ia_db')\gexec
    
    -- Crear usuario de aplicación (leyendo de variables de entorno)
    CREATE USER ${POSTGRES_APP_USER} WITH ENCRYPTED PASSWORD '${POSTGRES_APP_PASSWORD}';
    GRANT ALL PRIVILEGES ON DATABASE tutor_ia_db TO ${POSTGRES_APP_USER};
    
    -- Conectar a la base de datos de la aplicación
    \c tutor_ia_db
    
    -- Crear schema
    CREATE SCHEMA IF NOT EXISTS tutor_ia;
    GRANT ALL ON SCHEMA tutor_ia TO ${POSTGRES_APP_USER};
    
    -- Crear tablas iniciales
    CREATE TABLE IF NOT EXISTS tutor_ia.health_check (
        id SERIAL PRIMARY KEY,
        service_name VARCHAR(50) NOT NULL,
        status VARCHAR(20) NOT NULL,
        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Tabla para métricas de replicación (habilitada)
    CREATE TABLE IF NOT EXISTS tutor_ia.replication_metrics (
        id SERIAL PRIMARY KEY,
        lag_bytes BIGINT,
        lag_seconds FLOAT,
        measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    GRANT ALL ON ALL TABLES IN SCHEMA tutor_ia TO ${POSTGRES_APP_USER};
    GRANT ALL ON ALL SEQUENCES IN SCHEMA tutor_ia TO ${POSTGRES_APP_USER};

EOSQL
# --- FIN DE CAMBIOS ---

# Crear directorio de archivos WAL si no existe
mkdir -p /var/lib/postgresql/archive
chown postgres:postgres /var/lib/postgresql/archive

log "Configuración del Master completada"