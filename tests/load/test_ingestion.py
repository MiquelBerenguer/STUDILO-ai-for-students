import asyncio
import httpx
import aiofiles
import time
import os
import structlog

# --- Configuración ---
TARGET_URL = "http://localhost:8002/process"  # Endpoint de subida
FILE_PATH = os.path.join(os.path.dirname(__file__), "APUNTS DISEÑO DE SISTEMAS.pdf")  # Archivo a subir
NUM_REQUESTS = 100  # Total de archivos a simular
CONCURRENCY = 10  # Cuántos usuarios suben a la vez
# ---------------------

log = structlog.get_logger()
log.info(
    "Configuración del test de carga",
    url=TARGET_URL,
    file=FILE_PATH,
    total_requests=NUM_REQUESTS,
    concurrency=CONCURRENCY
)

# Cola para gestionar las tareas
queue = asyncio.Queue()

async def file_uploader(client: httpx.AsyncClient, worker_id: int):
    """
    Un worker que consume de la cola y sube el archivo.
    """
    while not queue.empty():
        try:
            job_num = await queue.get()
            log.info(f"[Worker {worker_id}] Iniciando subida #{job_num}")

            # Leer el archivo de forma asíncrona
            async with aiofiles.open(FILE_PATH, 'rb') as f:
                file_content = await f.read()
            
            files = {'file': (os.path.basename(FILE_PATH), file_content, 'application/pdf')}
            
            start_time = time.monotonic()
            response = await client.post(TARGET_URL, files=files, timeout=30.0)
            end_time = time.monotonic()
            
            duration = end_time - start_time
            
            if 200 <= response.status_code < 300:
                log.info(
                    f"[Worker {worker_id}] Éxito #{job_num}",
                    status=response.status_code,
                    job_id=response.json().get("job_id"),
                    duration_ms=f"{duration:.2f}s"
                )
            else:
                log.error(
                    f"[Worker {worker_id}] Error #{job_num}",
                    status=response.status_code,
                    response=response.text[:150], # Primeros 150 chars de la respuesta
                    duration_ms=f"{duration:.2f}s"
                )
                
        except Exception as e:
            log.error(f"[Worker {worker_id}] Excepción", error=str(e))
        finally:
            queue.task_done()

async def main():
    if not os.path.exists(FILE_PATH):
        log.error(f"Archivo de prueba no encontrado en: {FILE_PATH}")
        return

    log.warning("--- INICIANDO TEST DE CARGA EN 3 SEGUNDOS ---")
    log.warning("Abre tus dashboards de Grafana y RabbitMQ AHORA.")
    await asyncio.sleep(3)
    
    # Llenar la cola con números de trabajo
    for i in range(NUM_REQUESTS):
        await queue.put(i + 1)
    
    start_total_time = time.monotonic()
    
    async with httpx.AsyncClient() as client:
        # Crear los workers concurrentes
        workers = [
            asyncio.create_task(file_uploader(client, i))
            for i in range(CONCURRENCY)
        ]
        
        # Esperar a que la cola se procese
        await queue.join()
        
        # Cancelar los workers (ya no hay tareas)
        for worker in workers:
            worker.cancel()
            
    end_total_time = time.monotonic()
    total_duration = end_total_time - start_total_time
    
    log.info(
        "--- TEST DE CARGA COMPLETADO ---",
        total_duration=f"{total_duration:.2f}s",
        requests_per_second=f"{(NUM_REQUESTS / total_duration):.2f} req/s"
    )

if __name__ == "__main__":
    # Configuración de logging para que se vea bien
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )
    asyncio.run(main())