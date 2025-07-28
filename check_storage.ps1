# Script para verificar el almacenamiento de archivos en MinIO
Write-Host "=== VERIFICACIÓN DE ALMACENAMIENTO MINIO ===" -ForegroundColor Cyan

# Verificar que MinIO esté funcionando
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:9001/minio/health/live" -Method Get
    Write-Host "MinIO está funcionando correctamente" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: MinIO no está accesible en http://localhost:9001" -ForegroundColor Red
    Write-Host "Verifica que el servicio esté corriendo con: docker-compose ps minio" -ForegroundColor Yellow
    exit
}

# Verificar jobs en Redis
Write-Host "`n=== JOBS EN REDIS ===" -ForegroundColor Yellow

try {
    # Usar curl para verificar los jobs que creamos
    $job1 = "f9eaa3e1-ff18-4a6c-bc97-cb229e84e183"  # PDF job
    $job2 = "003c7ad5-2a59-4fa8-a622-8adaf33d7c51"  # TXT job
    
    Write-Host "Verificando Job PDF: $job1" -ForegroundColor Cyan
    $response1 = Invoke-RestMethod -Uri "http://localhost:8002/status/$job1" -Method Get
    $response1 | ConvertTo-Json -Depth 10
    
    Write-Host "`nVerificando Job TXT: $job2" -ForegroundColor Cyan
    $response2 = Invoke-RestMethod -Uri "http://localhost:8002/status/$job2" -Method Get
    $response2 | ConvertTo-Json -Depth 10
    
}
catch {
    Write-Host "Error verificando jobs: $_" -ForegroundColor Red
}

# Verificar cola de RabbitMQ
Write-Host "`n=== COLA DE PROCESAMIENTO ===" -ForegroundColor Yellow

try {
    $queueResponse = Invoke-RestMethod -Uri "http://localhost:8002/queue/size" -Method Get
    Write-Host "Tamaño de la cola: $($queueResponse.queue_size) trabajos pendientes" -ForegroundColor Green
}
catch {
    Write-Host "Error verificando cola: $_" -ForegroundColor Red
}

Write-Host "`n=== INSTRUCCIONES PARA VER ARCHIVOS ===" -ForegroundColor Magenta
Write-Host "1. Abre tu navegador y ve a: http://localhost:9001" -ForegroundColor Cyan
Write-Host "2. Login con: minioadmin / minioadmin" -ForegroundColor Cyan
Write-Host "3. Busca el bucket 'documents'" -ForegroundColor Cyan
Write-Host "4. Dentro encontrarás: uploads/[job_id]/[filename]" -ForegroundColor Cyan
Write-Host "5. Los archivos están organizados por job_id" -ForegroundColor Cyan

Write-Host "`n=== FIN DE VERIFICACIÓN ===" -ForegroundColor Cyan 