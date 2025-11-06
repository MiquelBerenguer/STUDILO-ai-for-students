const LLMProvider = require('../utils/llmProvider');
const winston = require('winston');

// Configurar logger específico para el controlador
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'llm-controller' },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

// Inicializar el proveedor LLM
const llmProvider = new LLMProvider();

// Estadísticas de uso (en memoria por ahora)
let usageStats = {
  totalRequests: 0,
  successfulRequests: 0,
  failedRequests: 0,
  providersUsed: {
    openai: 0,
    anthropic: 0
  },
  averageResponseTime: 0,
  startTime: new Date()
};

// === FUNCIONES AUXILIARES ===

// Actualizar estadísticas
const updateStats = (provider, success, responseTime) => {
  usageStats.totalRequests++;
  if (success) {
    usageStats.successfulRequests++;
  } else {
    usageStats.failedRequests++;
  }
  if (provider && usageStats.providersUsed[provider] !== undefined) {
    usageStats.providersUsed[provider]++;
  }
  
  // Calcular tiempo promedio de respuesta
  usageStats.averageResponseTime = 
    (usageStats.averageResponseTime + responseTime) / 2;
};

// Prompts especializados para educación
const EDUCATIONAL_PROMPTS = {
  examGeneration: `
    Eres un experto tutor educativo especializado en crear exámenes personalizados.
    
    INSTRUCCIONES:
    1. Genera un examen basado en las notas proporcionadas
    2. Adapta el nivel de dificultad según se solicite
    3. Asegúrate de que las preguntas sean relevantes y educativas
    4. Incluye variedad en los tipos de pregunta
    5. Proporciona respuestas correctas al final
    
    FORMATO DE RESPUESTA:
    - Título del examen
    - Instrucciones claras
    - Preguntas numeradas
    - Respuestas correctas al final
  `,
  
  studentAnalysis: `
    Eres un psicólogo educativo especializado en análisis de rendimiento estudiantil.
    
    INSTRUCCIONES:
    1. Analiza el rendimiento y preferencias del estudiante
    2. Identifica fortalezas y áreas de mejora
    3. Proporciona recomendaciones personalizadas
    4. Sugiere estrategias de estudio efectivas
    5. Estima probabilidades realistas de éxito
    
    FORMATO DE RESPUESTA:
    - Análisis de fortalezas
    - Áreas de mejora identificadas
    - Recomendaciones específicas
    - Estrategias sugeridas
  `,
  
  studyPlanGeneration: `
    Eres un experto en planificación educativa y gestión del tiempo.
    
    INSTRUCCIONES:
    1. Crea un plan de estudio realista y efectivo
    2. Considera las limitaciones de tiempo del estudiante
    3. Prioriza temas según importancia y dificultad
    4. Incluye descansos y técnicas de estudio
    5. Adapta el plan al estilo de aprendizaje
    
    FORMATO DE RESPUESTA:
    - Cronograma semanal detallado
    - Objetivos diarios específicos
    - Técnicas de estudio recomendadas
    - Hitos y evaluaciones
  `
};

// === CONTROLADORES PRINCIPALES ===

// 1. Generar respuesta general
const generateResponse = async (req, res) => {
  const startTime = Date.now();
  let provider = null;
  
  try {
    const { prompt, context, model, maxTokens, temperature } = req.validatedBody;
    
    logger.info('Generando respuesta', { 
      promptLength: prompt.length,
      hasContext: !!context,
      requestedModel: model
    });
    
    // Construir prompt completo
    let fullPrompt = prompt;
    if (context) {
      fullPrompt = `Contexto: ${context}\n\nPregunta: ${prompt}`;
    }
    
    // Generar respuesta usando el proveedor LLM
    const result = await llmProvider.generateCompletion({
      prompt: fullPrompt,
      model: model,
      maxTokens: maxTokens,
      temperature: temperature
    });
    
    provider = result.provider;
    const responseTime = Date.now() - startTime;
    updateStats(provider, true, responseTime);
    
    logger.info('Respuesta generada exitosamente', {
      provider: result.provider,
      responseTime: responseTime,
      tokensUsed: result.tokensUsed
    });
    
    res.json({
      success: true,
      data: {
        response: result.content,
        metadata: {
          provider: result.provider,
          model: result.model,
          tokensUsed: result.tokensUsed,
          responseTime: responseTime
        }
      }
    });
    
  } catch (error) {
    const responseTime = Date.now() - startTime;
    updateStats(provider, false, responseTime);
    
    logger.error('Error generando respuesta', {
      error: error.message,
      stack: error.stack,
      responseTime: responseTime
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error al generar respuesta',
        details: error.message,
        status: 500
      }
    });
  }
};

// 2. Generar examen personalizado
const generateExam = async (req, res) => {
  const startTime = Date.now();
  let provider = null;
  
  try {
    const { subject, notes, examType, difficulty, questionsCount, timeLimit } = req.validatedBody;
    
    logger.info('Generando examen', {
      subject,
      examType,
      difficulty,
      questionsCount,
      notesLength: notes.length
    });
    
    // Construir prompt especializado para exámenes
    const examPrompt = `
      ${EDUCATIONAL_PROMPTS.examGeneration}
      
      DATOS DEL EXAMEN:
      - Materia: ${subject}
      - Tipo: ${examType}
      - Dificultad: ${difficulty}
      - Número de preguntas: ${questionsCount}
      ${timeLimit ? `- Tiempo límite: ${timeLimit} minutos` : ''}
      
      NOTAS DE ESTUDIO:
      ${notes}
      
      Por favor, genera el examen siguiendo exactamente el formato especificado.
    `;
    
    const result = await llmProvider.generateCompletion({
      prompt: examPrompt,
      maxTokens: 3000,
      temperature: 0.7
    });
    
    provider = result.provider;
    const responseTime = Date.now() - startTime;
    updateStats(provider, true, responseTime);
    
    logger.info('Examen generado exitosamente', {
      provider: result.provider,
      responseTime: responseTime,
      subject: subject
    });
    
    res.json({
      success: true,
      data: {
        exam: result.content,
        metadata: {
          subject,
          examType,
          difficulty,
          questionsCount,
          timeLimit,
          provider: result.provider,
          generatedAt: new Date().toISOString(),
          responseTime: responseTime
        }
      }
    });
    
  } catch (error) {
    const responseTime = Date.now() - startTime;
    updateStats(provider, false, responseTime);
    
    logger.error('Error generando examen', {
      error: error.message,
      subject: req.validatedBody?.subject
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error al generar examen',
        details: error.message,
        status: 500
      }
    });
  }
};

// 3. Corregir examen
const correctExam = async (req, res) => {
  const startTime = Date.now();
  let provider = null;
  
  try {
    const { exam, answers, rubric } = req.body;
    
    logger.info('Corrigiendo examen', {
      hasExam: !!exam,
      hasAnswers: !!answers,
      hasRubric: !!rubric
    });
    
    const correctionPrompt = `
      Eres un profesor experto encargado de corregir este examen.
      
      INSTRUCCIONES DE CORRECCIÓN:
      1. Evalúa cada respuesta objetivamente
      2. Proporciona feedback constructivo
      3. Asigna puntuaciones justas
      4. Identifica áreas de mejora
      5. Sugiere recursos adicionales si es necesario
      
      EXAMEN ORIGINAL:
      ${exam}
      
      RESPUESTAS DEL ESTUDIANTE:
      ${answers}
      
      ${rubric ? `RÚBRICA DE EVALUACIÓN:\n${rubric}` : ''}
      
      Por favor, proporciona una corrección detallada con puntuación y feedback.
    `;
    
    const result = await llmProvider.generateCompletion({
      prompt: correctionPrompt,
      maxTokens: 2500,
      temperature: 0.3 // Menos creatividad para correcciones
    });
    
    provider = result.provider;
    const responseTime = Date.now() - startTime;
    updateStats(provider, true, responseTime);
    
    res.json({
      success: true,
      data: {
        correction: result.content,
        metadata: {
          provider: result.provider,
          correctedAt: new Date().toISOString(),
          responseTime: responseTime
        }
      }
    });
    
  } catch (error) {
    const responseTime = Date.now() - startTime;
    updateStats(provider, false, responseTime);
    
    logger.error('Error corrigiendo examen', { error: error.message });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error al corregir examen',
        details: error.message,
        status: 500
      }
    });
  }
};

// 4. Analizar estudiante
const analyzeStudent = async (req, res) => {
  const startTime = Date.now();
  let provider = null;
  
  try {
    const { studentId, performance, preferences } = req.validatedBody;
    
    logger.info('Analizando estudiante', { studentId });
    
    const analysisPrompt = `
      ${EDUCATIONAL_PROMPTS.studentAnalysis}
      
      DATOS DEL ESTUDIANTE:
      - ID: ${studentId}
      - Rendimiento: ${JSON.stringify(performance, null, 2)}
      ${preferences ? `- Preferencias: ${JSON.stringify(preferences, null, 2)}` : ''}
      
      Por favor, proporciona un análisis completo y recomendaciones personalizadas.
    `;
    
    const result = await llmProvider.generateCompletion({
      prompt: analysisPrompt,
      maxTokens: 2000,
      temperature: 0.6
    });
    
    provider = result.provider;
    const responseTime = Date.now() - startTime;
    updateStats(provider, true, responseTime);
    
    res.json({
      success: true,
      data: {
        analysis: result.content,
        studentId: studentId,
        metadata: {
          provider: result.provider,
          analyzedAt: new Date().toISOString(),
          responseTime: responseTime
        }
      }
    });
    
  } catch (error) {
    const responseTime = Date.now() - startTime;
    updateStats(provider, false, responseTime);
    
    logger.error('Error analizando estudiante', { error: error.message });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error al analizar estudiante',
        details: error.message,
        status: 500
      }
    });
  }
};

// 5. Generar plan de estudio
const generateStudyPlan = async (req, res) => {
  const startTime = Date.now();
  let provider = null;
  
  try {
    const { subject, examDate, currentLevel, timeAvailable, goals } = req.body;
    
    logger.info('Generando plan de estudio', { subject, examDate });
    
    const studyPlanPrompt = `
      ${EDUCATIONAL_PROMPTS.studyPlanGeneration}
      
      PARÁMETROS DEL PLAN:
      - Materia: ${subject}
      ${examDate ? `- Fecha del examen: ${examDate}` : ''}
      ${currentLevel ? `- Nivel actual: ${currentLevel}` : ''}
      ${timeAvailable ? `- Tiempo disponible: ${timeAvailable} horas/día` : ''}
      ${goals ? `- Objetivos: ${goals}` : ''}
      
      Genera un plan de estudio detallado y realista.
    `;
    
    const result = await llmProvider.generateCompletion({
      prompt: studyPlanPrompt,
      maxTokens: 2500,
      temperature: 0.7
    });
    
    provider = result.provider;
    const responseTime = Date.now() - startTime;
    updateStats(provider, true, responseTime);
    
    res.json({
      success: true,
      data: {
        studyPlan: result.content,
        metadata: {
          subject,
          examDate,
          provider: result.provider,
          createdAt: new Date().toISOString(),
          responseTime: responseTime
        }
      }
    });
    
  } catch (error) {
    const responseTime = Date.now() - startTime;
    updateStats(provider, false, responseTime);
    
    logger.error('Error generando plan de estudio', { error: error.message });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error al generar plan de estudio',
        details: error.message,
        status: 500
      }
    });
  }
};

// 6. Calcular probabilidad de aprobado
const calculatePassProbability = async (req, res) => {
  const startTime = Date.now();
  let provider = null;
  
  try {
    const { studentData, examHistory, studyProgress } = req.body;
    
    const probabilityPrompt = `
      Eres un experto en análisis predictivo educativo. 
      
      Analiza los siguientes datos y calcula una probabilidad realista de que el estudiante apruebe:
      
      DATOS DEL ESTUDIANTE:
      ${JSON.stringify(studentData, null, 2)}
      
      HISTORIAL DE EXÁMENES:
      ${JSON.stringify(examHistory, null, 2)}
      
      PROGRESO DE ESTUDIO:
      ${JSON.stringify(studyProgress, null, 2)}
      
      Proporciona:
      1. Probabilidad de aprobado (0-100%)
      2. Factores que influyen positivamente
      3. Factores de riesgo
      4. Recomendaciones para mejorar la probabilidad
    `;
    
    const result = await llmProvider.generateCompletion({
      prompt: probabilityPrompt,
      maxTokens: 1500,
      temperature: 0.4
    });
    
    provider = result.provider;
    const responseTime = Date.now() - startTime;
    updateStats(provider, true, responseTime);
    
    res.json({
      success: true,
      data: {
        probabilityAnalysis: result.content,
        metadata: {
          provider: result.provider,
          calculatedAt: new Date().toISOString(),
          responseTime: responseTime
        }
      }
    });
    
  } catch (error) {
    const responseTime = Date.now() - startTime;
    updateStats(provider, false, responseTime);
    
    logger.error('Error calculando probabilidad', { error: error.message });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error al calcular probabilidad de aprobado',
        details: error.message,
        status: 500
      }
    });
  }
};

// === CONTROLADORES DE ADMINISTRACIÓN ===

// Estado de los proveedores
const getProvidersStatus = async (req, res) => {
  try {
    const status = await llmProvider.getProvidersStatus();
    
    res.json({
      success: true,
      data: {
        providers: status,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    logger.error('Error obteniendo estado de proveedores', { error: error.message });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error al obtener estado de proveedores',
        status: 500
      }
    });
  }
};

// Estadísticas de uso
const getUsageStats = (req, res) => {
  const uptime = Date.now() - usageStats.startTime.getTime();
  
  res.json({
    success: true,
    data: {
      ...usageStats,
      uptime: uptime,
      successRate: usageStats.totalRequests > 0 
        ? (usageStats.successfulRequests / usageStats.totalRequests * 100).toFixed(2) + '%'
        : '0%'
    }
  });
};

// Test de proveedor (solo desarrollo)
const testProvider = async (req, res) => {
  try {
    const { provider } = req.body;
    
    const testResult = await llmProvider.testProvider(provider);
    
    res.json({
      success: true,
      data: {
        provider: provider,
        status: testResult.status,
        responseTime: testResult.responseTime,
        message: testResult.message
      }
    });
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: {
        message: 'Error testing provider',
        details: error.message
      }
    });
  }
};

module.exports = {
  generateResponse,
  generateExam,
  correctExam,
  analyzeStudent,
  generateStudyPlan,
  calculatePassProbability,
  getProvidersStatus,
  getUsageStats,
  testProvider
};