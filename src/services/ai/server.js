const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const dotenv = require('dotenv');
const winston = require('winston');

// Cargar variables de entorno
dotenv.config();

// Configurar logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'ai-service' },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

// Crear aplicación Express
const app = express();
const PORT = process.env.PORT || 3002;

// Middleware de seguridad
app.use(helmet());
app.use(cors({
  origin: [
    'http://localhost:3000', // API Gateway
    'http://localhost:3001'  // Auth Service
  ],
  credentials: true
}));

// Middleware para parsing
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Middleware de logging
app.use((req, res, next) => {
  logger.info(`${req.method} ${req.path}`, {
    ip: req.ip,
    userAgent: req.get('User-Agent')
  });
  next();
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'ok',
    service: 'ai-service',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: process.env.NODE_ENV,
    version: '1.0.0'
  });
});

// Información del servicio
app.get('/', (req, res) => {
  res.json({
    name: 'Tutor IA - AI Service',
    version: '1.0.0',
    description: 'Servicio de integración con LLMs para tutoría educativa',
    endpoints: {
      health: '/health',
      ai: '/api/ai/*'
    },
    providers: {
      default: process.env.DEFAULT_LLM_PROVIDER,
      fallback: process.env.FALLBACK_LLM_PROVIDER
    }
  });
});

// Importar y usar rutas de AI
const aiRoutes = require('./routes/ai');
app.use('/api/ai', aiRoutes);

// Middleware de manejo de errores
app.use((err, req, res, next) => {
  logger.error('Error en el servidor:', {
    error: err.message,
    stack: err.stack,
    url: req.url,
    method: req.method
  });

  res.status(err.status || 500).json({
    error: {
      message: err.message || 'Error interno del servidor',
      status: err.status || 500,
      timestamp: new Date().toISOString()
    }
  });
});

// Middleware para rutas no encontradas
app.use('*', (req, res) => {
  res.status(404).json({
    error: {
      message: 'Ruta no encontrada',
      status: 404,
      path: req.originalUrl
    }
  });
});

// Iniciar servidor
app.listen(PORT, () => {
  logger.info(`🚀 Servicio AI iniciado en puerto ${PORT}`);
  logger.info(`📊 Ambiente: ${process.env.NODE_ENV}`);
  logger.info(`🤖 Proveedor principal: ${process.env.DEFAULT_LLM_PROVIDER}`);
  logger.info(`🔄 Proveedor fallback: ${process.env.FALLBACK_LLM_PROVIDER}`);
  logger.info(`🌐 Health check: http://localhost:${PORT}/health`);
});

// Manejo graceful de shutdown
process.on('SIGTERM', () => {
  logger.info('SIGTERM recibido, cerrando servidor...');
  process.exit(0);
});

process.on('SIGINT', () => {
  logger.info('SIGINT recibido, cerrando servidor...');
  process.exit(0);
});

module.exports = app;