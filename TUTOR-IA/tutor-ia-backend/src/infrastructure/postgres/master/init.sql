-- Crear usuario de replicación
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'Mikibasket7';

-- Crear slot de replicación
SELECT * FROM pg_create_physical_replication_slot('replica_1_slot');

-- Crear base de datos para la aplicación
CREATE DATABASE tutor_ia_db;

-- Crear usuario de aplicación
CREATE USER REDACTED WITH ENCRYPTED PASSWORD 'app_secure_password_123';
GRANT ALL PRIVILEGES ON DATABASE tutor_ia_db TO REDACTED;