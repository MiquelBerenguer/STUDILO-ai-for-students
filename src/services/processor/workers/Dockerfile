FROM python:3.11-slim

# Instalar dependencias del sistema (Poppler para pdf2image)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Copiar requirements e instalar
COPY src/services/processor/workers/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copiar el código del worker
COPY src/services/processor/workers/ .

# 3. COPIAR LA LIBRERÍA SHARED (¡La clave!)
# Copiamos src/shared dentro de /app/shared para poder importarlo
COPY src/shared/ /app/shared/

# Configurar PYTHONPATH para que Python encuentre 'shared'
ENV PYTHONPATH=/app

CMD ["python", "pdf_worker_multi_queue.py"]