#!/bin/sh
# startup.sh (para postgres-replica)

set -e

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] (Replica) $1"
}

log "Iniciando script de startup de la réplica..."

# Variables de entorno (pasadas desde docker-compose)
# POSTGRES_REPL_USER, POSTGRES_REPL_PASSWORD, POSTGRES_APP_USER, POSTGRES_APP_PASSWORD
# POSTGRES_USER, POSTGRES_PASSWORD (del master)

# Directorio de datos de la réplica
PGDATA="/var/lib/postgresql/data"

# --- 1. Esperar a que el master esté listo ---
log "Esperando a que postgres-master (en ${PG_MASTER_HOST}) esté disponible..."
until pg_isready -h "${PG_MASTER_HOST}" -p "5432" -U "${POSTGRES_REPL_USER}"; do
    log "Master no está listo... esperando 5 segundos."
    sleep 5
done
log "¡Master detectado! Continuamos."

# --- 2. Limpiar directorio de datos antiguo ---
# Comprobar si el directorio PGDATA está vacío o no
if [ "$(ls -A $PGDATA)" ]; then
    log "El directorio PGDATA no está vacío. Limpiando datos antiguos..."
    rm -rf $PGDATA/*
    log "Datos antiguos eliminados."
else
    log "El directorio PGDATA está vacío. No se necesita limpieza."
fi

# --- 3. Ejecutar pg_basebackup ---
log "Iniciando pg_basebackup desde ${PG_MASTER_HOST}..."

# Creamos un .pgpass para que pg_basebackup no pida contraseña
# Formato: hostname:port:database:username:password
echo "${PG_MASTER_HOST}:5432:replication:${POSTGRES_REPL_USER}:${POSTGRES_REPL_PASSWORD}" > ~/.pgpass
chmod 0600 ~/.pgpass

pg_basebackup -h "${PG_MASTER_HOST}" -p 5432 -U "${POSTGRES_REPL_USER}" -D "${PGDATA}" -Fp -Xs -P -R -S "replica_1_slot"

# -h: Host del Master
# -U: Usuario de Replicación
# -D: Directorio de datos de destino (de la réplica)
# -Fp: Formato (plain)
# -Xs: Incluir WALs (stream)
# -P: Progreso
# -R: Escribir la configuración de recovery (primary_conninfo y standby.signal) automáticamente
# -S: Usar el slot de replicación que creamos en el master

log "Backup base completado."
rm ~/.pgpass # Limpiar el archivo de contraseña

# --- 4. Ajustar permisos ---
# pg_basebackup debería ajustar los permisos, pero por si acaso:
chmod 0700 "${PGDATA}"

log "Configuración de la réplica completada. El contenedor 'command' tomará el control."