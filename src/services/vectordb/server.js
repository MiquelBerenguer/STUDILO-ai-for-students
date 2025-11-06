const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const dotenv = require('dotenv');
const winston = require('winston');
const path = require('path');
const fs = require('fs');

// Cargar variables de entorno
dotenv.config();

// Crear directorios necesarios
const createDirectories = () => {
  const dirs = [
    './uploads',
    './data',
    './logs',
    './cache'
  ];
  
  dirs.forEach(dir => {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  });
};

createDirectories();

// Configurar logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'vectordb-service' },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    }),
    new winston.transports.File({
      filename: process.env.LOG_FILE || 'logs/vectordb-service.log'
    })
  ]
});

// Crear aplicación Express
const app = express();
const PORT = process.env.PORT || 3003;

// Middleware de seguridad
app.use(helmet());
app.use(cors({
  origin: [
    'http://localhost:3000', // API Gateway
    'http://localhost:3001', // Auth Service
    'http://localhost:3002'  // AI Service
  ],
  credentials: true
}));

// Middleware para parsing con límite de archivos
app.use(express.json({ 
  limit: process.env.MAX_FILE_SIZE || '10mb' 
}));
app.use(express.urlencoded({ 
  extended: true,
  limit: process.env.MAX_FILE_SIZE || '10mb' 
}));

// Middleware de logging
app.use((req, res, next) => {
  const startTime = Date.now();
  
  logger.info(`${req.method} ${req.path}`, {
    ip: req.ip,
    userAgent: req.get('User-Agent'),
    contentLength: req.get('Content-Length')
  });
  
  // Log response time
  res.on('finish', () => {
    const responseTime = Date.now() - startTime;
    logger.info(`Response completed`, {
      method: req.method,
      path: req.path,
      statusCode: res.statusCode,
      responseTime: `${responseTime}ms`
    });
  });
  
  next();
});

// Health check endpoint
app.get('/health', async (req, res) => {
  try {
    // Verificar estado de las dependencias principales
    const health = {
      status: 'ok',
      service: 'vectordb-service',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      environment: process.env.NODE_ENV,
      version: '1.0.0',
      database: {
        type: process.env.VECTOR_DB_TYPE,
        status: 'connected' // TODO: verificar conexión real
      },
      storage: {
        uploadPath: process.env.UPLOAD_PATH,
        databasePath: process.env.DATABASE_PATH,
        cacheEnabled: process.env.ENABLE_SEMANTIC_CACHE === 'true'
      },
      embeddings: {
        model: process.env.EMBEDDING_MODEL,
        dimensions: process.env.EMBEDDING_DIMENSIONS,
        provider: 'openai'
      }
    };
    
    res.status(200).json(health);
  } catch (error) {
    logger.error('Health check failed', { error: error.message });
    res.status(503).json({
      status: 'error',
      service: 'vectordb-service',
      error: error.message
    });
  }
});

// Información del servicio
app.get('/', (req, res) => {
  res.json({
    name: 'Tutor IA - Vector Database Service',
    version: '1.0.0',
    description: 'Servicio de base de datos vectorial para búsqueda semántica en contenido educativo',
    capabilities: {
      embedding: 'Generación de embeddings de documentos',
      storage: 'Almacenamiento vectorial eficiente',
      search: 'Búsqueda semántica inteligente',
      preprocessing: 'Procesamiento automático de texto'
    },
    endpoints: {
      health: '/health',
      vectordb: '/api/vectordb/*',
      upload: '/api/vectordb/upload',
      search: '/api/vectordb/search',
      embeddings: '/api/vectordb/embeddings/*'
    },
    configuration: {
      vectorDbType: process.env.VECTOR_DB_TYPE,
      embeddingModel: process.env.EMBEDDING_MODEL,
      maxChunkSize: process.env.MAX_CHUNK_SIZE,
      similarityThreshold: process.env.SIMILARITY_THRESHOLD
    },
    limits: {
      maxFileSize: process.env.MAX_FILE_SIZE,
      maxRequestsPerMinute: process.env.MAX_REQUESTS_PER_MINUTE,
      maxEmbeddingsPerRequest: process.env.MAX_EMBEDDINGS_PER_REQUEST
    }
  });
});

// Importar y usar rutas de Vector DB
const vectordbRoutes = require('./routes/vectordb');
app.use('/api/vectordb', vectordbRoutes);

// Endpoint para estadísticas del servicio
app.get('/api/stats', (req, res) => {
  const stats = {
    service: 'vectordb-service',
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    timestamp: new Date().toISOString(),
    configuration: {
      vectorDbType: process.env.VECTOR_DB_TYPE,
      embeddingModel: process.env.EMBEDDING_MODEL,
      cacheEnabled: process.env.ENABLE_SEMANTIC_CACHE === 'true'
    },
    // TODO: Añadir estadísticas reales de uso
    usage: {
      totalDocuments: 0,
      totalEmbeddings: 0,
      totalSearches: 0,
      averageSearchTime: 0
    }
  };
  
  res.json(stats);
});

// Middleware para servir archivos estáticos (uploads)
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

// Middleware de manejo de errores
app.use((err, req, res, next) => {
  logger.error('Error en el servidor Vector DB:', {
    error: err.message,
    stack: err.stack,
    url: req.url,
    method: req.method
  });

  // Errores específicos del Vector DB
  if (err.code === 'EMBEDDING_FAILED') {
    return res.status(500).json({
      error: {
        message: 'Error al generar embeddings',
        details: err.message,
        status: 500
      }
    });
  }

  if (err.code === 'VECTOR_SEARCH_FAILED') {
    return res.status(500).json({
      error: {
        message: 'Error en búsqueda vectorial',
        details: err.message,
        status: 500
      }
    });
  }

  if (err.code === 'FILE_TOO_LARGE') {
    return res.status(413).json({
      error: {
        message: 'Archivo demasiado grande',
        maxSize: process.env.MAX_FILE_SIZE,
        status: 413
      }
    });
  }

  res.status(err.status || 500).json({
    error: {
      message: err.message || 'Error interno del servidor Vector DB',
      status: err.status || 500,
      timestamp: new Date().toISOString()
    }
  });
});

// Middleware para rutas no encontradas
app.use('*', (req, res) => {
  res.status(404).json({
    error: {
      message: 'Endpoint no encontrado en Vector DB Service',
      status: 404,
      path: req.originalUrl,
      availableEndpoints: [
        'GET /health',
        'GET /api/stats',
        'POST /api/vectordb/upload',
        'POST /api/vectordb/search',
        'GET /api/vectordb/documents',
        'DELETE /api/vectordb/documents/:id'
      ]
    }
  });
});

// Inicializar base de datos vectorial al arrancar
const initializeVectorDB = async () => {
  try {
    logger.info('Inicializando base de datos vectorial...');
    
    // TODO: Aquí se inicializará la conexión con la base de datos vectorial
    // según la configuración (local, Pinecone, ChromaDB, etc.)
    
    const vectorDbType = process.env.VECTOR_DB_TYPE || 'local';
    logger.info(`Tipo de Vector DB: ${vectorDbType}`);
    
    // Verificar que el modelo de embeddings esté configurado
    if (!process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY === 'tu_clave_openai_aqui') {
      logger.warn('⚠️  OpenAI API Key no configurada - embeddings no funcionarán');
    }
    
    logger.info('✅ Vector DB inicializada correctamente');
    
  } catch (error) {
    logger.error('❌ Error inicializando Vector DB:', error.message);
  }
};

// Iniciar servidor
app.listen(PORT, async () => {
  logger.info(`🚀 Servicio Vector DB iniciado en puerto ${PORT}`);
  logger.info(`📊 Ambiente: ${process.env.NODE_ENV}`);
  logger.info(`🗄️ Tipo de Vector DB: ${process.env.VECTOR_DB_TYPE}`);
  logger.info(`🧠 Modelo de embeddings: ${process.env.EMBEDDING_MODEL}`);
  logger.info(`📁 Directorio de uploads: ${process.env.UPLOAD_PATH}`);
  logger.info(`🌐 Health check: http://localhost:${PORT}/health`);
  
  // Inicializar Vector DB
  await initializeVectorDB();
});

// Manejo graceful de shutdown
process.on('SIGTERM', () => {
  logger.info('SIGTERM recibido, cerrando servidor Vector DB...');
  // TODO: Cerrar conexiones de base de datos vectorial
  process.exit(0);
});

process.on('SIGINT', () => {
  logger.info('SIGINT recibido, cerrando servidor Vector DB...');
  // TODO: Cerrar conexiones de base de datos vectorial
  process.exit(0);
});

// Manejo de errores no capturados
process.on('unhandledRejection', (reason, promise) => {
  logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
});

process.on('uncaughtException', (error) => {
  logger.error('Uncaught Exception:', error);
  process.exit(1);
});

module.exports = app;