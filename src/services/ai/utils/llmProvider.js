const OpenAI = require('openai');
const Anthropic = require('@anthropic-ai/sdk');
const axios = require('axios');
const winston = require('winston');

// Configurar logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'llm-provider' },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

class LLMProvider {
  constructor() {
    // Configuración de proveedores
    this.providers = {
      openai: null,
      anthropic: null
    };
    
    // Estado de salud de proveedores
    this.providerHealth = {
      openai: { available: false, lastCheck: null, errorCount: 0 },
      anthropic: { available: false, lastCheck: null, errorCount: 0 }
    };
    
    // Configuración de reintentos
    this.maxRetries = parseInt(process.env.MAX_RETRIES) || 3;
    this.retryDelay = parseInt(process.env.RETRY_DELAY_MS) || 1000;
    this.requestTimeout = parseInt(process.env.REQUEST_TIMEOUT_MS) || 30000;
    
    // Mapeo de modelos por proveedor
    this.modelMapping = {
      'gpt-4': { provider: 'openai', model: 'gpt-4' },
      'gpt-3.5-turbo': { provider: 'openai', model: 'gpt-3.5-turbo' },
      'claude-3': { provider: 'anthropic', model: 'claude-3-sonnet-20240229' },
      'claude-3-haiku': { provider: 'anthropic', model: 'claude-3-haiku-20240307' }
    };
    
    // Inicializar proveedores
    this.initializeProviders();
    
    // Verificar salud de proveedores cada 5 minutos
    setInterval(() => {
      this.checkProvidersHealth();
    }, 5 * 60 * 1000);
  }

  // === INICIALIZACIÓN ===
  
  initializeProviders() {
    try {
      // Inicializar OpenAI
      if (process.env.OPENAI_API_KEY && process.env.OPENAI_API_KEY !== 'tu_clave_openai_aqui') {
        this.providers.openai = new OpenAI({
          apiKey: process.env.OPENAI_API_KEY,
          timeout: this.requestTimeout
        });
        this.providerHealth.openai.available = true;
        logger.info('OpenAI provider inicializado');
      } else {
        logger.warn('OpenAI API key no configurada');
      }
      
      // Inicializar Anthropic
      if (process.env.ANTHROPIC_API_KEY && process.env.ANTHROPIC_API_KEY !== 'tu_clave_anthropic_aqui') {
        this.providers.anthropic = new Anthropic({
          apiKey: process.env.ANTHROPIC_API_KEY,
          timeout: this.requestTimeout
        });
        this.providerHealth.anthropic.available = true;
        logger.info('Anthropic provider inicializado');
      } else {
        logger.warn('Anthropic API key no configurada');
      }
      
      // Verificar que al menos un proveedor esté disponible
      if (!this.providerHealth.openai.available && !this.providerHealth.anthropic.available) {
        logger.error('ADVERTENCIA: Ningún proveedor LLM configurado correctamente');
      }
      
    } catch (error) {
      logger.error('Error inicializando proveedores', { error: error.message });
    }
  }

  // === VERIFICACIÓN DE SALUD ===
  
  async checkProvidersHealth() {
    logger.info('Verificando salud de proveedores...');
    
    // Verificar OpenAI
    if (this.providers.openai) {
      try {
        const startTime = Date.now();
        const response = await this.providers.openai.chat.completions.create({
          model: 'gpt-3.5-turbo',
          messages: [{ role: 'user', content: 'Test' }],
          max_tokens: 5
        });
        
        this.providerHealth.openai = {
          available: true,
          lastCheck: new Date(),
          errorCount: 0,
          responseTime: Date.now() - startTime
        };
        
        logger.info('OpenAI health check: OK');
        
      } catch (error) {
        this.providerHealth.openai.errorCount++;
        this.providerHealth.openai.available = this.providerHealth.openai.errorCount < 3;
        this.providerHealth.openai.lastCheck = new Date();
        
        logger.warn('OpenAI health check failed', { 
          error: error.message,
          errorCount: this.providerHealth.openai.errorCount
        });
      }
    }
    
    // Verificar Anthropic
    if (this.providers.anthropic) {
      try {
        const startTime = Date.now();
        const response = await this.providers.anthropic.messages.create({
          model: 'claude-3-haiku-20240307',
          max_tokens: 5,
          messages: [{ role: 'user', content: 'Test' }]
        });
        
        this.providerHealth.anthropic = {
          available: true,
          lastCheck: new Date(),
          errorCount: 0,
          responseTime: Date.now() - startTime
        };
        
        logger.info('Anthropic health check: OK');
        
      } catch (error) {
        this.providerHealth.anthropic.errorCount++;
        this.providerHealth.anthropic.available = this.providerHealth.anthropic.errorCount < 3;
        this.providerHealth.anthropic.lastCheck = new Date();
        
        logger.warn('Anthropic health check failed', { 
          error: error.message,
          errorCount: this.providerHealth.anthropic.errorCount
        });
      }
    }
  }

  // === LÓGICA DE SELECCIÓN DE PROVEEDOR ===
  
  selectBestProvider(requestedModel = null) {
    // Si se especifica un modelo, usar su proveedor
    if (requestedModel && this.modelMapping[requestedModel]) {
      const mapping = this.modelMapping[requestedModel];
      if (this.providerHealth[mapping.provider].available) {
        return mapping.provider;
      }
    }
    
    // Lógica de fallback inteligente
    const defaultProvider = process.env.DEFAULT_LLM_PROVIDER || 'openai';
    const fallbackProvider = process.env.FALLBACK_LLM_PROVIDER || 'anthropic';
    
    // Intentar proveedor por defecto
    if (this.providerHealth[defaultProvider].available) {
      return defaultProvider;
    }
    
    // Usar fallback
    if (this.providerHealth[fallbackProvider].available) {
      logger.warn(`Usando proveedor fallback: ${fallbackProvider}`);
      return fallbackProvider;
    }
    
    // Si ninguno está disponible, intentar con el que tenga menos errores
    const providers = Object.keys(this.providerHealth);
    providers.sort((a, b) => 
      this.providerHealth[a].errorCount - this.providerHealth[b].errorCount
    );
    
    if (providers.length > 0 && this.providers[providers[0]]) {
      logger.warn(`Usando proveedor con menos errores: ${providers[0]}`);
      return providers[0];
    }
    
    throw new Error('Ningún proveedor LLM disponible');
  }

  // === MÉTODOS PRINCIPALES ===
  
  async generateCompletion(options = {}) {
    const {
      prompt,
      model = null,
      maxTokens = 1000,
      temperature = 0.7,
      systemPrompt = null
    } = options;
    
    if (!prompt) {
      throw new Error('Prompt es requerido');
    }
    
    const selectedProvider = this.selectBestProvider(model);
    logger.info('Generando completion', { 
      provider: selectedProvider,
      model: model,
      promptLength: prompt.length,
      maxTokens: maxTokens
    });
    
    // Intentar con reintentos
    for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
      try {
        const result = await this.callProvider(selectedProvider, {
          prompt,
          model,
          maxTokens,
          temperature,
          systemPrompt
        });
        
        logger.info('Completion generado exitosamente', {
          provider: selectedProvider,
          attempt: attempt,
          tokensUsed: result.tokensUsed
        });
        
        return result;
        
      } catch (error) {
        logger.warn(`Intento ${attempt} falló`, {
          provider: selectedProvider,
          error: error.message
        });
        
        // Si no es el último intento, esperar antes del siguiente
        if (attempt < this.maxRetries) {
          await this.sleep(this.retryDelay * attempt);
          
          // Intentar con proveedor fallback en el último intento
          if (attempt === this.maxRetries - 1) {
            try {
              const fallbackProvider = selectedProvider === 'openai' ? 'anthropic' : 'openai';
              if (this.providerHealth[fallbackProvider].available) {
                logger.info(`Intentando con proveedor fallback: ${fallbackProvider}`);
                return await this.callProvider(fallbackProvider, {
                  prompt,
                  model: null, // Usar modelo por defecto del proveedor
                  maxTokens,
                  temperature,
                  systemPrompt
                });
              }
            } catch (fallbackError) {
              logger.error('Proveedor fallback también falló', {
                error: fallbackError.message
              });
            }
          }
        }
      }
    }
    
    throw new Error(`Falló después de ${this.maxRetries} intentos con todos los proveedores`);
  }

  // === LLAMADAS A PROVEEDORES ESPECÍFICOS ===
  
  async callProvider(provider, options) {
    const { prompt, model, maxTokens, temperature, systemPrompt } = options;
    const startTime = Date.now();
    
    switch (provider) {
      case 'openai':
        return await this.callOpenAI(prompt, model, maxTokens, temperature, systemPrompt, startTime);
      
      case 'anthropic':
        return await this.callAnthropic(prompt, model, maxTokens, temperature, systemPrompt, startTime);
      
      default:
        throw new Error(`Proveedor no soportado: ${provider}`);
    }
  }
  
  async callOpenAI(prompt, model, maxTokens, temperature, systemPrompt, startTime) {
    if (!this.providers.openai) {
      throw new Error('OpenAI provider no inicializado');
    }
    
    const messages = [];
    
    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }
    
    messages.push({ role: 'user', content: prompt });
    
    const requestModel = model && this.modelMapping[model]?.provider === 'openai' 
      ? this.modelMapping[model].model 
      : 'gpt-3.5-turbo';
    
    const response = await this.providers.openai.chat.completions.create({
      model: requestModel,
      messages: messages,
      max_tokens: maxTokens,
      temperature: temperature,
      timeout: this.requestTimeout
    });
    
    const responseTime = Date.now() - startTime;
    
    return {
      content: response.choices[0].message.content,
      provider: 'openai',
      model: requestModel,
      tokensUsed: response.usage?.total_tokens || 0,
      responseTime: responseTime
    };
  }
  
  async callAnthropic(prompt, model, maxTokens, temperature, systemPrompt, startTime) {
    if (!this.providers.anthropic) {
      throw new Error('Anthropic provider no inicializado');
    }
    
    const requestModel = model && this.modelMapping[model]?.provider === 'anthropic'
      ? this.modelMapping[model].model
      : 'claude-3-haiku-20240307';
    
    const messages = [{ role: 'user', content: prompt }];
    
    const requestOptions = {
      model: requestModel,
      max_tokens: maxTokens,
      temperature: temperature,
      messages: messages
    };
    
    if (systemPrompt) {
      requestOptions.system = systemPrompt;
    }
    
    const response = await this.providers.anthropic.messages.create(requestOptions);
    
    const responseTime = Date.now() - startTime;
    
    return {
      content: response.content[0].text,
      provider: 'anthropic',
      model: requestModel,
      tokensUsed: response.usage?.input_tokens + response.usage?.output_tokens || 0,
      responseTime: responseTime
    };
  }

  // === MÉTODOS DE UTILIDAD ===
  
  async sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
  
  async getProvidersStatus() {
    return {
      openai: {
        available: this.providerHealth.openai.available,
        lastCheck: this.providerHealth.openai.lastCheck,
        errorCount: this.providerHealth.openai.errorCount,
        responseTime: this.providerHealth.openai.responseTime,
        configured: !!this.providers.openai
      },
      anthropic: {
        available: this.providerHealth.anthropic.available,
        lastCheck: this.providerHealth.anthropic.lastCheck,
        errorCount: this.providerHealth.anthropic.errorCount,
        responseTime: this.providerHealth.anthropic.responseTime,
        configured: !!this.providers.anthropic
      }
    };
  }
  
  async testProvider(providerName) {
    const startTime = Date.now();
    
    try {
      const testPrompt = 'Responde solo con "OK" si puedes leer esto.';
      
      const result = await this.callProvider(providerName, {
        prompt: testPrompt,
        maxTokens: 10,
        temperature: 0
      });
      
      return {
        status: 'success',
        provider: providerName,
        responseTime: Date.now() - startTime,
        message: 'Proveedor funcionando correctamente',
        response: result.content
      };
      
    } catch (error) {
      return {
        status: 'error',
        provider: providerName,
        responseTime: Date.now() - startTime,
        message: error.message
      };
    }
  }
  
  // === MÉTODOS PARA CONFIGURACIÓN ===
  
  getAvailableModels() {
    return Object.keys(this.modelMapping);
  }
  
  getModelInfo(modelName) {
    return this.modelMapping[modelName] || null;
  }
  
  // === ESTIMACIÓN DE COSTOS ===
  
  estimateCost(provider, model, inputTokens, outputTokens) {
    // Precios aproximados (actualizar según pricing real)
    const pricing = {
      openai: {
        'gpt-4': { input: 0.03, output: 0.06 },
        'gpt-3.5-turbo': { input: 0.0015, output: 0.002 }
      },
      anthropic: {
        'claude-3-sonnet-20240229': { input: 0.003, output: 0.015 },
        'claude-3-haiku-20240307': { input: 0.00025, output: 0.00125 }
      }
    };
    
    const providerPricing = pricing[provider];
    if (!providerPricing || !providerPricing[model]) {
      return { estimated: false, cost: 0 };
    }
    
    const modelPricing = providerPricing[model];
    const inputCost = (inputTokens / 1000) * modelPricing.input;
    const outputCost = (outputTokens / 1000) * modelPricing.output;
    
    return {
      estimated: true,
      cost: inputCost + outputCost,
      breakdown: {
        input: inputCost,
        output: outputCost,
        inputTokens: inputTokens,
        outputTokens: outputTokens
      }
    };
  }
}

module.exports = LLMProvider;