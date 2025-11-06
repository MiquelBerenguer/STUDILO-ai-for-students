// Configuración centralizada para el servicio Vector DB
const path = require('path');

const config = {
  // Configuración del servidor
  server: {
    port: parseInt(process.env.PORT) || 3003,
    environment: process.env.NODE_ENV || 'development',
    corsOrigins: [
      'http://localhost:3000', // API Gateway
      'http://localhost:3001', // Auth Service
      'http://localhost:3002'  // AI Service
    ]
  },

  // Configuración de embeddings
  embeddings: {
    provider: 'openai', // openai, cohere (futuro)
    model: process.env.EMBEDDING_MODEL || 'text-embedding-ada-002',
    dimensions: parseInt(process.env.EMBEDDING_DIMENSIONS) || 1536,
    batchSize: 100, // Máximo embeddings por batch
    timeout: 30000, // 30 segundos
    retryAttempts: 3,
    retryDelay: 1000
  },

  // Configuración de base de datos vectorial
  vectorDatabase: {
    type: process.env.VECTOR_DB_TYPE || 'local',
    
    // SQLite local (desarrollo)
    local: {
      databasePath: process.env.DATABASE_PATH || './data/vectordb.sqlite',
      enableWAL: true, // Write-Ahead Logging para mejor rendimiento
      connectionPool: {
        min: 1,
        max: 10
      }
    },

    // Pinecone (producción)
    pinecone: {
      apiKey: process.env.PINECONE_API_KEY,
      environment: process.env.PINECONE_ENVIRONMENT || 'us-west1-gcp-free',
      indexName: process.env.PINECONE_INDEX_NAME || 'tutor-ia-embeddings',
      metricType: 'cosine',
      pods: 1,
      replicas: 1
    },

    // ChromaDB (alternativa local)
    chroma: {
      host: process.env.CHROMA_HOST || 'localhost',
      port: parseInt(process.env.CHROMA_PORT) || 8000,
      collectionName: process.env.CHROMA_COLLECTION_NAME || 'educational_documents',
      persistDirectory: './data/chroma'
    }
  },

  // Configuración de procesamiento de texto
  textProcessing: {
    preprocessing: process.env.TEXT_PREPROCESSING === 'true',
    removeStopwords: process.env.REMOVE_STOPWORDS === 'true',
    language: process.env.LANGUAGE || 'es',
    minTextLength: parseInt(process.env.MIN_TEXT_LENGTH) || 50,
    maxTextLength: parseInt(process.env.MAX_TEXT_LENGTH) || 5000,
    
    // Configuración de chunking
    chunking: {
      maxChunkSize: parseInt(process.env.MAX_CHUNK_SIZE) || 1000,
      chunkOverlap: parseInt(process.env.CHUNK_OVERLAP) || 200,
      preserveSentences: true, // Evitar cortar en medio de oraciones
      minChunkSize: 100
    }
  },

  // Configuración de búsqueda
  search: {
    defaultSimilarityThreshold: parseFloat(process.env.SIMILARITY_THRESHOLD) || 0.75,
    maxSearchResults: parseInt(process.env.MAX_SEARCH_RESULTS) || 10,
    enableSemanticCache: process.env.ENABLE_SEMANTIC_CACHE === 'true',
    
    // Algoritmos de búsqueda disponibles
    algorithms: {
      cosine: {
        name: 'Similitud Coseno',
        description: 'Mejor para la mayoría de casos',
        threshold: 0.75
      },
      euclidean: {
        name: 'Distancia Euclidiana', 
        description: 'Más sensible a magnitudes',
        threshold: 0.5
      },
      dotProduct: {
        name: 'Producto Punto',
        description: 'Rápido pero menos preciso',
        threshold: 0.8
      }
    }
  },

  // Configuración de archivos
  files: {
    uploadPath: process.env.UPLOAD_PATH || './uploads',
    maxFileSize: process.env.MAX_FILE_SIZE || '10MB',
    allowedExtensions: (process.env.ALLOWED_EXTENSIONS || 'pdf,txt,docx,md').split(','),
    
    // Configuración por tipo de archivo
    processors: {
      pdf: {
        extractImages: false,
        preserveLayout: false,
        maxPages: 100
      },
      docx: {
        includeFootnotes: true,
        includeHeaders: false,
        preserveFormatting: false
      },
      txt: {
        encoding: 'utf8',
        detectEncoding: true
      }
    }
  },

  // Configuración de rate limiting
  rateLimiting: {
    general: {
      windowMs: 60 * 1000, // 1 minuto
      maxRequests: parseInt(process.env.MAX_REQUESTS_PER_MINUTE) || 100,
      message: 'Demasiadas peticiones. Intenta más tarde.'
    },
    embeddings: {
      windowMs: 60 * 1000,
      maxRequests: 20, // Más restrictivo para embeddings
      message: 'Límite de embeddings excedido. Son operaciones costosas.'
    },
    upload: {
      windowMs: 60 * 1000,
      maxRequests: 10, // Muy restrictivo para uploads
      message: 'Límite de subidas excedido.'
    }
  },

  // Configuración de cache
  cache: {
    embeddings: {
      enabled: process.env.CACHE_EMBEDDINGS === 'true',
      ttl: parseInt(process.env.CACHE_TTL) || 3600, // 1 hora
      maxSize: parseInt(process.env.CACHE_MAX_SIZE) || 1000,
      algorithm: 'LRU' // Least Recently Used
    },
    search: {
      enabled: process.env.ENABLE_SEMANTIC_CACHE === 'true',
      ttl: 1800, // 30 minutos
      maxSize: 500
    }
  },

  // Configuración de logging
  logging: {
    level: process.env.LOG_LEVEL || 'info',
    file: process.env.LOG_FILE || 'logs/vectordb-service.log',
    logEmbeddings: process.env.LOG_EMBEDDINGS === 'true',
    logSearchQueries: process.env.LOG_SEARCH_QUERIES === 'true',
    logPerformance: true,
    
    // Configuración detallada por operación
    operations: {
      upload: { level: 'info', includeFileDetails: true },
      embedding: { level: 'debug', includeTokenCount: true },
      search: { level: 'info', includeResultCount: true },
      error: { level: 'error', includeStackTrace: true }
    }
  },

  // Configuración de backup
  backup: {
    enabled: process.env.ENABLE_BACKUP === 'true',
    interval: process.env.BACKUP_INTERVAL || '24h',
    retentionDays: 30,
    location: './backups',
    compression: true
  },

  // Configuración de rendimiento
  performance: {
    batchSize: parseInt(process.env.BATCH_SIZE) || 100,
    parallelProcessing: process.env.PARALLEL_PROCESSING === 'true',
    maxConcurrentRequests: parseInt(process.env.MAX_CONCURRENT_REQUESTS) || 10,
    
    // Optimizaciones de memoria
    memory: {
      maxHeapSize: '512MB',
      gcOptimization: true,
      memoryWarningThreshold: 0.8
    }
  },

  // URLs de servicios integrados
  services: {
    aiService: process.env.AI_SERVICE_URL || 'http://localhost:3002',
    authService: process.env.AUTH_SERVICE_URL || 'http://localhost:3001',
    apiGateway: process.env.API_GATEWAY_URL || 'http://localhost:3000'
  },

  // Configuración educativa específica
  education: {
    // Clasificación de dificultad
    difficulties: {
      easy: {
        label: 'Fácil',
        description: 'Conceptos básicos e introductorios',
        color: '#4CAF50'
      },
      medium: {
        label: 'Medio',
        description: 'Conocimiento intermedio',
        color: '#FF9800'
      },
      hard: {
        label: 'Difícil',
        description: 'Conceptos avanzados y complejos',
        color: '#F44336'
      }
    },

    // Tipos de contenido educativo
    contentTypes: {
      notes: {
        label: 'Apuntes',
        description: 'Material de estudio principal',
        icon: '📝'
      },
      exam: {
        label: 'Examen',
        description: 'Evaluaciones y tests',
        icon: '📋'
      },
      summary: {
        label: 'Resumen',
        description: 'Síntesis de conceptos',
        icon: '📄'
      },
      exercise: {
        label: 'Ejercicio',
        description: 'Práctica y problemas',
        icon: '🔢'
      },
      reference: {
        label: 'Referencia',
        description: 'Material de consulta',
        icon: '📚'
      }
    },

    // Materias populares
    subjects: [
      'Matemáticas', 'Física', 'Química', 'Biología',
      'Historia', 'Literatura', 'Inglés', 'Filosofía',
      'Economía', 'Programación', 'Derecho', 'Medicina'
    ]
  }
};

// === FUNCIONES DE UTILIDAD ===

// Obtener configuración por entorno
const getEnvironmentConfig = () => {
  const env = process.env.NODE_ENV || 'development';
  
  switch (env) {
    case 'production':
      return {
        ...config,
        vectorDatabase: { ...config.vectorDatabase, type: 'pinecone' },
        logging: { ...config.logging, level: 'warn' },
        cache: { ...config.cache, embeddings: { ...config.cache.embeddings, enabled: true } }
      };
    
    case 'test':
      return {
        ...config,
        server: { ...config.server, port: 0 }, // Puerto aleatorio para tests
        vectorDatabase: { ...config.vectorDatabase, local: { ...config.vectorDatabase.local, databasePath: ':memory:' } },
        logging: { ...config.logging, level: 'error' }
      };
    
    default: // development
      return config;
  }
};

// Validar configuración
const validateConfig = () => {
  const errors = [];
  
  // Validar embeddings
  if (!process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY === 'tu_clave_openai_aqui') {
    errors.push('OpenAI API Key no configurada');
  }
  
  // Validar directorios
  const requiredDirs = [
    config.files.uploadPath,
    path.dirname(config.vectorDatabase.local.databasePath),
    path.dirname(config.logging.file)
  ];
  
  // Validar dimensiones de embeddings
  if (config.embeddings.dimensions < 1 || config.embeddings.dimensions > 3072) {
    errors.push('Dimensiones de embedding inválidas');
  }
  
  return {
    isValid: errors.length === 0,
    errors: errors
  };
};

// Obtener configuración optimizada para el tipo de operación
const getOptimizedConfig = (operationType) => {
  const baseConfig = getEnvironmentConfig();
  
  switch (operationType) {
    case 'bulk_upload':
      return {
        ...baseConfig,
        performance: {
          ...baseConfig.performance,
          batchSize: 50, // Menor batch para uploads masivos
          maxConcurrentRequests: 5
        }
      };
    
    case 'real_time_search':
      return {
        ...baseConfig,
        search: {
          ...baseConfig.search,
          maxSearchResults: 5, // Menos resultados para mayor velocidad
          defaultSimilarityThreshold: 0.8 // Mayor precisión
        }
      };
    
    default:
      return baseConfig;
  }
};

// Generar configuración para monitoreo
const getMonitoringConfig = () => {
  return {
    service: 'vectordb-service',
    version: '1.0.0',
    environment: config.server.environment,
    metrics: {
      enableCustomMetrics: true,
      collectInterval: 30000, // 30 segundos
      metricsEndpoint: '/metrics'
    },
    healthCheck: {
      endpoint: '/health',
      timeout: 5000,
      dependencies: [
        { name: 'openai', type: 'external' },
        { name: 'database', type: 'internal' },
        { name: 'filesystem', type: 'internal' }
      ]
    }
  };
};

module.exports = {
  config,
  getEnvironmentConfig,
  validateConfig,
  getOptimizedConfig,
  getMonitoringConfig
};
