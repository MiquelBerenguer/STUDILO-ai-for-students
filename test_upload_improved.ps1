# Script mejorado para probar el servicio de procesamiento
# Soporta archivos PDF y TXT automáticamente

param(
    [string]$FilePath = "test_files\test_document.pdf"
)

$uri = "http://localhost:8002/process"
$fullPath = Join-Path $PWD $FilePath

Write-Host "=== PRUEBA DE SERVICIO DE PROCESAMIENTO ===" -ForegroundColor Cyan
Write-Host "Archivo: $fullPath" -ForegroundColor Yellow

if (-not (Test-Path $fullPath)) {
    Write-Host "ERROR: El archivo no existe en $fullPath" -ForegroundColor Red
    Write-Host "Archivos disponibles en test_files:" -ForegroundColor Yellow
    Get-ChildItem "test_files" | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Gray }
    exit
}

# Detectar tipo de archivo y Content-Type
$fileExtension = [System.IO.Path]::GetExtension($fullPath).ToLower()
$fileName = [System.IO.Path]::GetFileName($fullPath)

# Mapear extensiones a Content-Types
$contentTypeMap = @{
    ".pdf" = "application/pdf"
    ".txt" = "text/plain"
    ".png" = "image/png"
    ".jpg" = "image/jpeg"
    ".jpeg" = "image/jpeg"
}

$contentType = $contentTypeMap[$fileExtension]
if (-not $contentType) {
    Write-Host "ERROR: Formato no soportado: $fileExtension" -ForegroundColor Red
    Write-Host "Formatos soportados: PDF, TXT, PNG, JPG, JPEG" -ForegroundColor Yellow
    exit
}

Write-Host "Tipo de archivo: $fileExtension" -ForegroundColor Green
Write-Host "Content-Type: $contentType" -ForegroundColor Green

try {
    # Leer el archivo
    $fileBytes = [System.IO.File]::ReadAllBytes($fullPath)
    
    # Crear el boundary para multipart/form-data
    $boundary = [System.Guid]::NewGuid().ToString()
    
    # Construir el cuerpo de la petición
    $LF = "`r`n"
    $bodyLines = @(
        "--$boundary",
        "Content-Disposition: form-data; name=`"file`"; filename=`"$fileName`"",
        "Content-Type: $contentType",
        "",
        [System.Text.Encoding]::UTF8.GetString($fileBytes),
        "--$boundary--"
    ) -join $LF
    
    # Convertir a bytes
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyLines)
    
    Write-Host "Enviando archivo al servidor..." -ForegroundColor Yellow
    
    # Hacer la petición
    $response = Invoke-RestMethod -Uri $uri -Method Post -ContentType "multipart/form-data; boundary=$boundary" -Body $bodyBytes
    
    # Mostrar la respuesta
    Write-Host "EXITO - Respuesta del servidor:" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
    
    # Extraer job_id si existe
    if ($response.job_id) {
        Write-Host "Job ID: $($response.job_id)" -ForegroundColor Cyan
        Write-Host "Para verificar el estado: http://localhost:8002/status/$($response.job_id)" -ForegroundColor Cyan
        Write-Host "Para ver metricas: http://localhost:8002/metrics" -ForegroundColor Cyan
    }
}
catch {
    Write-Host "ERROR:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    
    # Mostrar detalles adicionales si es un error HTTP
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "Detalles del error: $responseBody" -ForegroundColor Red
    }
}

Write-Host "=== FIN DE PRUEBA ===" -ForegroundColor Cyan 