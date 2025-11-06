const express = require('express');
const router = express.Router();
const { RateLimiterMemory } = require('rate-limiter-flexible');
const Joi = require('joi');
const llmController = require('../controllers/llmController');

// Rate limiter: 30 requests por minuto por IP
const rateLimiter = new RateLimiterMemory({
  keyPrefix: 'ai_service',
  points: 30, // Número de requests
  duration: 60, // Por 60 segundos
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
        message: 'Demasiadas peticiones. Intenta de nuevo más tarde.',
        retryAfter: secs,
        status: 429
      }
    });
  }
};

// Esquemas de validación con Joi
const schemas = {
  generateResponse: Joi.object({
    prompt: Joi.string().required().min(1).max(5000),
    context: Joi.string().optional().max(10000),
    model: Joi.string().optional().valid('gpt-4', 'gpt-3.5-turbo', 'claude-3'),
    maxTokens: Joi.number().optional().min(1).max(4000).default(1000),
    temperature: Joi.number().optional().min(0).max(2).default(0.7)
  }),

  generateExam: Joi.object({
    subject: Joi.string().required().min(1).max(200),
    notes: Joi.string().required().min(10).max(50000),
    examType: Joi.string().required().valid('test', 'theory', 'problems', 'mixed', 'oral'),
    difficulty: Joi.string().optional().valid('easy', 'medium', 'hard').default('medium'),
    questionsCount: Joi.number().optional().min(1).max(50).default(10),
    timeLimit: Joi.number().optional().min(5).max(180) // minutos
  }),

  analyzeStudent: Joi.object({
    studentId: Joi.string().required(),
    performance: Joi.object({
      averageScore: Joi.number().min(0).max(100),
      completedExams: Joi.number().min(0),
      studyHours: Joi.number().min(0),
      subjects: Joi.array().items(Joi.string())
    }).required(),
    preferences: Joi.object({
      studyStyle: Joi.string().valid('visual', 'auditory', 'kinesthetic'),
      difficulty: Joi.string().valid('easy', 'medium', 'hard'),
      timeAvailable: Joi.number().min(1).max(24) // horas por día
    }).optional()
  })
};

// Middleware de validación
const validate = (schema) => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req.body);
    if (error) {
      return res.status(400).json({
        error: {
          message: 'Datos de entrada inválidos',
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
    message: 'Servicio AI funcionando correctamente',
    timestamp: new Date().toISOString(),
    availableEndpoints: [
      'POST /generate - Generar respuesta con LLM',
      'POST /exam/generate - Generar examen personalizado', 
      'POST /student/analyze - Analizar perfil de estudiante',
      'POST /study-plan - Crear plan de estudio',
      'GET /providers/status - Estado de proveedores LLM'
    ]
  });
});

// 1. Generar respuesta general con LLM
router.post('/generate', 
  rateLimitMiddleware,
  validate(schemas.generateResponse),
  llmController.generateResponse
);

// 2. Generar examen personalizado
router.post('/exam/generate',
  rateLimitMiddleware,
  validate(schemas.generateExam),
  llmController.generateExam
);

// 3. Corregir examen
router.post('/exam/correct',
  rateLimitMiddleware,
  llmController.correctExam
);

// 4. Analizar perfil de estudiante
router.post('/student/analyze',
  rateLimitMiddleware,
  validate(schemas.analyzeStudent),
  llmController.analyzeStudent
);

// 5. Generar plan de estudio personalizado
router.post('/study-plan',
  rateLimitMiddleware,
  llmController.generateStudyPlan
);

// 6. Calcular probabilidad de aprobado
router.post('/student/probability',
  rateLimitMiddleware,
  llmController.calculatePassProbability
);

// === RUTAS DE ADMINISTRACIÓN ===

// Estado de los proveedores LLM
router.get('/providers/status', llmController.getProvidersStatus);

// Estadísticas de uso
router.get('/stats', llmController.getUsageStats);

// === RUTAS DE DESARROLLO/DEBUG ===

// Solo en desarrollo
if (process.env.NODE_ENV === 'development') {
  // Test de conexión con proveedores
  router.post('/debug/test-provider', llmController.testProvider);
  
  // Limpiar cache
  router.post('/debug/clear-cache', (req, res) => {
    res.json({ message: 'Cache limpiado (simulado)' });
  });
}

// Middleware de manejo de errores específico para rutas AI
router.use((err, req, res, next) => {
  if (err.code === 'RATE_LIMIT_EXCEEDED') {
    return res.status(429).json({
      error: {
        message: 'Límite de peticiones excedido',
        status: 429
      }
    });
  }
  
  if (err.name === 'ValidationError') {
    return res.status(400).json({
      error: {
        message: 'Error de validación',
        details: err.message,
        status: 400
      }
    });
  }
  
  next(err);
});

module.exports = router;