# Script para probar ambos formatos: PDF y TXT
Write-Host "=== PRUEBA DE AMBOS FORMATOS ===" -ForegroundColor Magenta

# Probar con archivo PDF
Write-Host "Probando archivo PDF..." -ForegroundColor Yellow
.\test_upload_improved.ps1 -FilePath "test_files\test_document.pdf"

# Esperar un momento entre pruebas
Start-Sleep -Seconds 2

# Probar con archivo TXT
Write-Host "Probando archivo TXT..." -ForegroundColor Yellow
.\test_upload_improved.ps1 -FilePath "test_files\test_document.txt"

Write-Host "=== PRUEBAS COMPLETADAS ===" -ForegroundColor Magenta 