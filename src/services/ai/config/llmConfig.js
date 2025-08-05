// Configuración centralizada para el servicio LLM
const config = {
  // Configuración de proveedores
  providers: {
    openai: {
      name: 'OpenAI',
      models: {
        'gpt-4': {
          maxTokens: 8192,
          costPer1KInput: 0.03,
          costPer1KOutput: 0.06,
          description: 'Modelo más avanzado, mejor para tareas complejas'
        },
        'gpt-3.5-turbo': {
          maxTokens: 4096,
          costPer1KInput: 0.0015,
          costPer1KOutput: 0.002,
          description: 'Modelo rápido y económico para tareas generales'
        }
      },
      rateLimit: {
        requestsPerMinute: 3500,
        tokensPerMinute: 90000
      }
    },
    anthropic: {
      name: 'Anthropic',
      models: {
        'claude-3-sonnet-20240229': {
          maxTokens: 4096,
          costPer1KInput: 0.003,
          costPer1KOutput: 0.015,
          description: 'Modelo equilibrado de Claude 3'
        },
        'claude-3-haiku-20240307': {
          maxTokens: 4096,
          costPer1KInput: 0.00025,
          costPer1KOutput: 0.00125,
          description: 'Modelo más rápido y económico de Claude 3'
        }
      },
      rateLimit: {
        requestsPerMinute: 4000,
        tokensPerMinute: 40000
      }
    }
  },

  // Configuración de fallback
  fallback: {
    enabled: true,
    strategy: 'cost_optimized', // 'cost_optimized', 'performance', 'balanced'
    maxRetries: 3,
    retryDelay: 1000,
    timeout: 30000
  },

  // Configuración por tipo de tarea
  taskConfigs: {
    exam_generation: {
      preferredProvider: 'openai',
      preferredModel: 'gpt-4',
      temperature: 0.7,
      maxTokens: 3000,
      systemPrompt: 'Eres un experto tutor educativo especializado en crear exámenes.'
    },
    exam_correction: {
      preferredProvider: 'openai',
      preferredModel: 'gpt-4',
      temperature: 0.3,
      maxTokens: 2500,
      systemPrompt: 'Eres un profesor experto en corrección de exámenes.'
    },
    student_analysis: {
      preferredProvider: 'anthropic',
      preferredModel: 'claude-3-sonnet-20240229',
      temperature: 0.6,
      maxTokens: 2000,
      systemPrompt: 'Eres un psicólogo educativo especializado en análisis estudiantil.'
    },
    study_planning: {
      preferredProvider: 'openai',
      preferredModel: 'gpt-3.5-turbo',
      temperature: 0.7,
      maxTokens: 2500,
      systemPrompt: 'Eres un experto en planificación educativa.'
    },
    general_tutoring: {
      preferredProvider: 'openai',
      preferredModel: 'gpt-3.5-turbo',
      temperature: 0.7,
      maxTokens: 1500,
      systemPrompt: 'Eres un tutor educativo amigable y pedagógico.'
    }
  },

  // Configuración de calidad
  quality: {
    enableContentFiltering: true,
    enableResponseValidation: true,
    minResponseLength: 10,
    maxResponseLength: 5000
  },

  // Configuración de cache
  cache: {
    enabled: true,
    ttl: 3600, // 1 hora
    maxSize: 1000 // número de entradas
  },

  // Configuración de logs
  logging: {
    logRequests: true,
    logResponses: false, // Por seguridad
    logErrors: true,
    logPerformance: true
  }
};

// Función para obtener configuración por tarea
const getTaskConfig = (taskType) => {
  return config.taskConfigs[taskType] || config.taskConfigs.general_tutoring;
};

// Función para obtener el mejor modelo según estrategia
const getBestModel = (strategy = 'balanced', taskType = 'general_tutoring') => {
  const taskConfig = getTaskConfig(taskType);
  
  switch (strategy) {
    case 'cost_optimized':
      return {
        provider: 'openai',
        model: 'gpt-3.5-turbo'
      };
    
    case 'performance':
      return {
        provider: 'openai',
        model: 'gpt-4'
      };
    
    case 'balanced':
    default:
      return {
        provider: taskConfig.preferredProvider,
        model: taskConfig.preferredModel
      };
  }
};

// Función para calcular costo estimado
const estimateRequestCost = (provider, model, inputTokens, outputTokens) => {
  const providerConfig = config.providers[provider];
  if (!providerConfig || !providerConfig.models[model]) {
    return { error: 'Modelo no encontrado' };
  }
  
  const modelConfig = providerConfig.models[model];
  const inputCost = (inputTokens / 1000) * modelConfig.costPer1KInput;
  const outputCost = (outputTokens / 1000) * modelConfig.costPer1KOutput;
  
  return {
    totalCost: inputCost + outputCost,
    breakdown: {
      inputCost,
      outputCost,
      inputTokens,
      outputTokens
    }
  };
};

// Validar configuración al cargar
const validateConfig = () => {
  const requiredEnvVars = [
    'DEFAULT_LLM_PROVIDER',
    'FALLBACK_LLM_PROVIDER',
    'MAX_RETRIES',
    'REQUEST_TIMEOUT_MS'
  ];
  
  const missing = requiredEnvVars.filter(envVar => !process.env[envVar]);
  
  if (missing.length > 0) {
    console.warn(`⚠️  Variables de entorno faltantes: ${missing.join(', ')}`);
  }
  
  // Verificar que los proveedores por defecto existan
  const defaultProvider = process.env.DEFAULT_LLM_PROVIDER;
  const fallbackProvider = process.env.FALLBACK_LLM_PROVIDER;
  
  if (defaultProvider && !config.providers[defaultProvider]) {
    console.error(`❌ Proveedor por defecto inválido: ${defaultProvider}`);
  }
  
  if (fallbackProvider && !config.providers[fallbackProvider]) {
    console.error(`❌ Proveedor fallback inválido: ${fallbackProvider}`);
  }
  
  console.log('✅ Configuración LLM validada');
};

module.exports = {
  config,
  getTaskConfig,
  getBestModel,
  estimateRequestCost,
  validateConfig
};