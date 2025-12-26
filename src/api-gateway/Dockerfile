# src/api-gateway/Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Instalamos dependencias del sistema (curl para healthcheck, gcc para compilar libs)
RUN apt-get update && apt-get install -y curl gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Copiamos requirements y los instalamos
# Nota: Asumimos que requirements.txt está dentro de src/api-gateway/
COPY src/api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- COPIADO DE CÓDIGO ---
# Como el contexto es la raíz (.), copiamos manteniendo estructura

# 1. Copiamos shared (dependencia común)
COPY src/shared /app/src/shared

# 2. Copiamos services (porque importamos rutas de learning)
COPY src/services /app/src/services

# 3. Copiamos el código del gateway
# Lo copiamos directamente a /app porque main.py está en la raíz de api-gateway
COPY src/api-gateway /app

# Ajustamos PYTHONPATH para que Python encuentre 'src' y 'app'
ENV PYTHONPATH=/app

# Exponemos puerto
EXPOSE 8000

# CORRECCIÓN AQUÍ: Cambiamos "main:app" por "app.main:app"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]