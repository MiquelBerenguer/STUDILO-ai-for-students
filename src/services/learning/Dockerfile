# src/services/learning/Dockerfile

# Usamos la versión estable
FROM python:3.11-slim-bookworm

WORKDIR /app

# 1. Dependencias del sistema (WeasyPrint y gráficos)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copiar código
COPY . .

# --- FIX CRÍTICO: Añadimos el path para que encuentre 'src' ---
ENV PYTHONPATH=/app

# 4. Arranque
CMD ["uvicorn", "src.services.learning.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]