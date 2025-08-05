const express = require('express');
const router = express.Router();
const multer = require('multer');
const { RateLimiterMemory } = require('rate-limiter-flexible');
const Joi = require('joi');
const path = require('path');
const embeddingController = require('../controllers/embeddingController');

// Rate limiter: 100 requests por minuto por IP
const rateLimiter = new RateLimiterMemory({
  keyPrefix: 'vectordb_service',
  points: parseInt(process.env.MAX_REQUESTS_PER_MINUTE) || 100,
  duration: 60,
});

// Rate limiter específico para embeddings (más restrictivo)
const embeddingRateLimiter = new RateLimiterMemory({
  keyPrefix: 'vectordb_embeddings',
  points: 20, // Menos requests para embeddings (son costosos)
  duration: 60,
});

// Middleware de rate limiting
const rateLimitMiddleware = async (req, res, next) => {
  try {
    await rateLimiter.consume(req.ip);
    next();
  } catch (rejRes) {
    const secs = Math.round(rejRes.msBeforeNext / 1000) || 1;
    res.set('Retry-After', String(secs));
    res.status(429).json({
      error: {
        message: 'Demasiadas peticiones al Vector DB. Intenta de nuevo más tarde.',
        retryAfter: secs,
        status: 429
      }
    });
  }
};

// Rate limiting específico para embeddings
const embeddingRateLimitMiddleware = async (req, res, next) => {
  try {
    await embeddingRateLimiter.consume(req.ip);
    next();
  } catch (rejRes) {
    const secs = Math.round(rejRes.msBeforeNext / 1000) || 1;
    res.set('Retry-After', String(secs));
    res.status(429).json({
      error: {
        message: 'Límite de embeddings excedido. Los embeddings son costosos, espera un momento.',
        retryAfter: secs,
        status: 429
      }
    });
  }
};

// Configuración de multer para subida de archivos
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, process.env.UPLOAD_PATH || './uploads');
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, file.fieldname + '-' + uniqueSuffix + path.extname(file.originalname));
  }
});

const fileFilter = (req, file, cb) => {
  const allowedExtensions = (process.env.ALLOWED_EXTENSIONS || 'pdf,txt,docx,md').split(',');
  const fileExtension = path.extname(file.originalname).toLowerCase().slice(1);
  
  if (allowedExtensions.includes(fileExtension)) {
    cb(null, true);
  } else {
    cb(new Error(`Tipo de archivo no permitido. Permitidos: ${allowedExtensions.join(', ')}`), false);
  }
};

const upload = multer({
  storage: storage,
  fileFilter: fileFilter,
  limits: {
    fileSize: parseInt(process.env.MAX_FILE_SIZE?.replace('MB', '')) * 1024 * 1024 || 10 * 1024 * 1024 // 10MB default
  }
});

// Esquemas de validación con Joi
const schemas = {
  textEmbedding: Joi.object({
    text: Joi.string().required().min(parseInt(process.env.MIN_TEXT_LENGTH) || 50).max(parseInt(process.env.MAX_TEXT_LENGTH) || 5000),
    metadata: Joi.object({
      title: Joi.string().optional(),
      subject: Joi.string().optional(),
      author: Joi.string().optional(),
      tags: Joi.array().items(Joi.string()).optional(),
      difficulty: Joi.string().valid('easy', 'medium', 'hard').optional(),
      type: Joi.string().valid('notes', 'exam', 'summary', 'exercise').optional()
    }).optional(),
    userId: Joi.string().optional(),
    chunkSize: Joi.number().min(100).max(2000).optional()
  }),

  semanticSearch: Joi.object({
    query: Joi.string().required().min(3).max(500),
    limit: Joi.number().min(1).max(parseInt(process.env.MAX_SEARCH_RESULTS) || 10).optional(),
    threshold: Joi.number().min(0).max(1).optional(),
    filters: Joi.object({
      subject: Joi.string().optional(),
      difficulty: Joi.string().valid('easy', 'medium', 'hard').optional(),
      type: Joi.string().valid('notes', 'exam', 'summary', 'exercise').optional(),
      author: Joi.string().optional(),
      userId: Joi.string().optional()
    }).optional(),
    includeMetadata: Joi.boolean().optional().default(true)
  }),

  batchEmbedding: Joi.object({
    texts: Joi.array().items(Joi.string().min(10).max(2000)).required().min(1).max(parseInt(process.env.MAX_EMBEDDINGS_PER_REQUEST) || 50),
    metadata: Joi.array().items(Joi.object()).optional(),
    userId: Joi.string().optional()
  }),

  documentUpdate: Joi.object({
    title: Joi.string().optional(),
    metadata: Joi.object().optional(),
    tags: Joi.array().items(Joi.string()).optional()
  })
};

// Middleware de validación
const validate = (schema) => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req.body);
    if (error) {
      return res.status(400).json({
        error: {
          message: 'Datos de entrada inválidos para Vector DB',
          details: error.details.map(detail => detail.message),
          status: 400
        }
      });
    }
    req.validatedBody = value;
    next();
  };
};

// === RUTAS PRINCIPALES ===

// Test de conectividad
router.get('/test', (req, res) => {
  res.json({
    message: 'Servicio Vector DB funcionando correctamente',
    timestamp: new Date().toISOString(),
    configuration: {
      vectorDbType: process.env.VECTOR_DB_TYPE,
      embeddingModel: process.env.EMBEDDING_MODEL,
      maxChunkSize: process.env.MAX_CHUNK_SIZE,
      similarityThreshold: process.env.SIMILARITY_THRESHOLD
    },
    availableEndpoints: [
      'POST /upload - Subir y procesar documentos',
      'POST /embeddings/text - Generar embedding de texto',
      'POST /embeddings/batch - Generar embeddings en lote',
      'POST /search - Búsqueda semántica',
      'GET /documents - Listar documentos',
      'GET /documents/:id - Obtener documento específico',
      'PUT /documents/:id - Actualizar documento',
      'DELETE /documents/:id - Eliminar documento',
      'GET /collections - Listar colecciones',
      'POST /collections - Crear colección'
    ]
  });
});

// === GESTIÓN DE DOCUMENTOS ===

// 1. Subir y procesar documento
router.post('/upload',
  rateLimitMiddleware,
  upload.single('document'),
  embeddingController.uploadDocument
);

// 2. Subir múltiples documentos
router.post('/upload/batch',
  rateLimitMiddleware,
  upload.array('documents', 10),
  embeddingController.uploadBatchDocuments
);

// 3. Procesar texto directo (sin archivo)
router.post('/embeddings/text',
  rateLimitMiddleware,
  embeddingRateLimitMiddleware,
  validate(schemas.textEmbedding),
  embeddingController.processText
);

// 4. Generar embeddings en lote
router.post('/embeddings/batch',
  rateLimitMiddleware,
  embeddingRateLimitMiddleware,
  validate(schemas.batchEmbedding),
  embeddingController.batchEmbeddings
);

// === BÚSQUEDA SEMÁNTICA ===

// 5. Búsqueda semántica principal
router.post('/search',
  rateLimitMiddleware,
  validate(schemas.semanticSearch),
  embeddingController.semanticSearch
);

// 6. Búsqueda por similitud de documento
router.post('/search/similar/:documentId',
  rateLimitMiddleware,
  embeddingController.findSimilarDocuments
);

// 7. Búsqueda avanzada con filtros múltiples
router.post('/search/advanced',
  rateLimitMiddleware,
  embeddingController.advancedSearch
);

// === GESTIÓN DE DOCUMENTOS ===

// 8. Listar documentos con paginación
router.get('/documents',
  rateLimitMiddleware,
  embeddingController.getDocuments
);

// 9. Obtener documento específico
router.get('/documents/:id',
  rateLimitMiddleware,
  embeddingController.getDocument
);

// 10. Actualizar metadatos de documento
router.put('/documents/:id',
  rateLimitMiddleware,
  validate(schemas.documentUpdate),
  embeddingController.updateDocument
);

// 11. Eliminar documento
router.delete('/documents/:id',
  rateLimitMiddleware,
  embeddingController.deleteDocument
);

// === GESTIÓN DE COLECCIONES ===

// 12. Listar colecciones
router.get('/collections',
  rateLimitMiddleware,
  embeddingController.getCollections
);

// 13. Crear nueva colección
router.post('/collections',
  rateLimitMiddleware,
  embeddingController.createCollection
);

// 14. Obtener estadísticas de colección
router.get('/collections/:name/stats',
  rateLimitMiddleware,
  embeddingController.getCollectionStats
);

// === FUNCIONES DE UTILIDAD ===

// 15. Obtener embedding de texto (sin almacenar)
router.post('/embeddings/generate',
  rateLimitMiddleware,
  embeddingRateLimitMiddleware,
  embeddingController.generateEmbedding
);

// 16. Verificar calidad de embeddings
router.post('/embeddings/quality',
  rateLimitMiddleware,
  embeddingController.checkEmbeddingQuality
);

// 17. Reindexar documentos (mantenimiento)
router.post('/maintenance/reindex',
  rateLimitMiddleware,
  embeddingController.reindexDocuments
);

// 18. Limpiar cache de embeddings
router.post('/maintenance/clear-cache',
  rateLimitMiddleware,
  embeddingController.clearCache
);

// === ESTADÍSTICAS Y MONITOREO ===

// 19. Estadísticas de uso
router.get('/stats',
  rateLimitMiddleware,
  embeddingController.getUsageStats
);

// 20. Métricas de rendimiento
router.get('/metrics',
  rateLimitMiddleware,
  embeddingController.getPerformanceMetrics
);

// === FUNCIONES ESPECÍFICAS PARA EDUCACIÓN ===

// 21. Encontrar contenido relacionado para exámenes
router.post('/education/exam-content',
  rateLimitMiddleware,
  embeddingController.findExamContent
);

// 22. Sugerir material de estudio relacionado
router.post('/education/study-suggestions',
  rateLimitMiddleware,
  embeddingController.getStudySuggestions
);

// 23. Analizar gaps de conocimiento
router.post('/education/knowledge-gaps',
  rateLimitMiddleware,
  embeddingController.analyzeKnowledgeGaps
);

// === RUTAS DE DESARROLLO/DEBUG ===

// Solo en desarrollo
if (process.env.NODE_ENV === 'development') {
  // Test de embeddings
  router.post('/debug/test-embeddings', 
    embeddingController.testEmbeddings
  );
  
  // Comparar similitud entre textos
  router.post('/debug/compare-texts',
    embeddingController.compareTexts
  );
  
  // Visualizar embeddings (datos para gráficos)
  router.post('/debug/visualize-embeddings',
    embeddingController.visualizeEmbeddings
  );
}

// Middleware de manejo de errores específico para Vector DB
router.use((err, req, res, next) => {
  if (err.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({
      error: {
        message: 'Archivo demasiado grande',
        maxSize: process.env.MAX_FILE_SIZE,
        status: 413
      }
    });
  }
  
  if (err.code === 'LIMIT_FILE_COUNT') {
    return res.status(400).json({
      error: {
        message: 'Demasiados archivos',
        maxFiles: 10,
        status: 400
      }
    });
  }
  
  if (err.code === 'EMBEDDING_RATE_LIMIT') {
    return res.status(429).json({
      error: {
        message: 'Límite de embeddings excedido',
        status: 429
      }
    });
  }
  
  if (err.message.includes('Tipo de archivo no permitido')) {
    return res.status(400).json({
      error: {
        message: err.message,
        allowedTypes: process.env.ALLOWED_EXTENSIONS?.split(',') || ['pdf', 'txt', 'docx', 'md'],
        status: 400
      }
    });
  }
  
  next(err);
});

module.exports = router;