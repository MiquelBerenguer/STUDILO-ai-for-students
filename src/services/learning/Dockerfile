FROM python:3.11-slim

WORKDIR /app

# Instalamos dependencias básicas del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiamos requerimientos (crearemos este archivo en el paso 3)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código
COPY . .

# Comando por defecto (esto fallará si no hay código, pero permite construir)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]