# Tutor IA Platform

Sistema de tutoría inteligente con procesamiento de documentos y análisis educativo.

## 🚀 Inicio Rápido

1. **Clonar el repositorio**
   ```bash
   git clone <repository-url>
   cd tutor-ia-backend

Configurar variables de entorno
bashcp .env.example .env
# Editar .env con tus valores

Levantar los servicios
bashmake up

Verificar que todo está funcionando
bashmake ps


📋 Servicios
ServicioPuertoDescripciónAPI Gateway8080Punto de entrada principalAuth Service8081Autenticación y autorizaciónProcessor Service8082Procesamiento de documentosAI Service8083Integración con LLMsAnalytics Service8084Análisis y métricasPostgreSQL5432Base de datos principalRedis6379Cache y sesionesRabbitMQ5672/15672Cola de mensajesMinIO9000/9001Almacenamiento S3Prometheus9090MétricasGrafana3000Dashboards
🛠 Comandos Útiles
bash# Ver logs de todos los servicios
make logs

# Ver logs de un servicio específico
docker-compose logs -f auth-service

# Reiniciar un servicio
docker-compose restart auth-service

# Limpiar todo (⚠️ borra datos)
make clean
📚 Documentación

Arquitectura
API Reference
Runbooks
