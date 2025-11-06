const EmbeddingProvider = require('../utils/embeddingProvider');
const Document = require('../models/Document');
const winston = require('winston');
const fs = require('fs').promises;
const path = require('path');
const pdfParse = require('pdf-parse');
const mammoth = require('mammoth');
const { v4: uuidv4 } = require('uuid');

// Configurar logger específico para embeddings
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'embedding-controller' },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

// Inicializar el proveedor de embeddings
const embeddingProvider = new EmbeddingProvider();

// Estadísticas de uso del servicio
let usageStats = {
  totalDocuments: 0,
  totalEmbeddings: 0,
  totalSearches: 0,
  totalUploadedFiles: 0,
  averageProcessingTime: 0,
  averageSearchTime: 0,
  startTime: new Date(),
  embeddingsByType: {
    pdf: 0,
    txt: 0,
    docx: 0,
    direct_text: 0
  }
};

// Cache en memoria para embeddings frecuentes
const embeddingCache = new Map();
const CACHE_MAX_SIZE = parseInt(process.env.CACHE_MAX_SIZE) || 1000;
const CACHE_TTL = parseInt(process.env.CACHE_TTL) || 3600; // 1 hora

// === FUNCIONES AUXILIARES ===

// Actualizar estadísticas
const updateStats = (operation, processingTime, additionalData = {}) => {
  switch (operation) {
    case 'document_upload':
      usageStats.totalDocuments++;
      usageStats.totalUploadedFiles++;
      if (additionalData.fileType) {
        usageStats.embeddingsByType[additionalData.fileType]++;
      }
      break;
    case 'embedding_generation':
      usageStats.totalEmbeddings++;
      usageStats.averageProcessingTime = 
        (usageStats.averageProcessingTime + processingTime) / 2;
      break;
    case 'semantic_search':
      usageStats.totalSearches++;
      usageStats.averageSearchTime = 
        (usageStats.averageSearchTime + processingTime) / 2;
      break;
  }
};

// Procesar texto en chunks
const chunkText = (text, chunkSize = 1000, overlap = 200) => {
  const chunks = [];
  const textLength = text.length;
  
  for (let i = 0; i < textLength; i += chunkSize - overlap) {
    const chunk = text.slice(i, i + chunkSize);
    if (chunk.trim().length > 0) {
      chunks.push({
        text: chunk.trim(),
        startIndex: i,
        endIndex: Math.min(i + chunkSize, textLength)
      });
    }
  }
  
  return chunks;
};

// Extraer texto de diferentes tipos de archivo
const extractTextFromFile = async (filePath, fileType) => {
  try {
    switch (fileType.toLowerCase()) {
      case 'pdf':
        const pdfBuffer = await fs.readFile(filePath);
        const pdfData = await pdfParse(pdfBuffer);
        return pdfData.text;
      
      case 'docx':
        const docxResult = await mammoth.extractRawText({ path: filePath });
        return docxResult.value;
      
      case 'txt':
      case 'md':
        return await fs.readFile(filePath, 'utf8');
      
      default:
        throw new Error(`Tipo de archivo no soportado: ${fileType}`);
    }
  } catch (error) {
    logger.error('Error extrayendo texto del archivo', {
      filePath,
      fileType,
      error: error.message
    });
    throw error;
  }
};

// Limpiar y preprocesar texto
const preprocessText = (text) => {
  if (!process.env.TEXT_PREPROCESSING === 'true') {
    return text;
  }
  
  // Limpiar caracteres especiales y normalizar espacios
  let cleanText = text
    .replace(/\s+/g, ' ') // Múltiples espacios a uno
    .replace(/\n\s*\n/g, '\n') // Múltiples saltos de línea
    .trim();
  
  // Remover stopwords si está habilitado
  if (process.env.REMOVE_STOPWORDS === 'true') {
    // TODO: Implementar remoción de stopwords en español
    // Por ahora solo limpiamos texto básico
  }
  
  return cleanText;
};

// Gestión de cache
const getCachedEmbedding = (text) => {
  if (!process.env.CACHE_EMBEDDINGS === 'true') return null;
  
  const cacheKey = Buffer.from(text).toString('base64').slice(0, 50);
  const cached = embeddingCache.get(cacheKey);
  
  if (cached && (Date.now() - cached.timestamp) < CACHE_TTL * 1000) {
    return cached.embedding;
  }
  
  return null;
};

const setCachedEmbedding = (text, embedding) => {
  if (!process.env.CACHE_EMBEDDINGS === 'true') return;
  
  const cacheKey = Buffer.from(text).toString('base64').slice(0, 50);
  
  // Limpiar cache si está lleno
  if (embeddingCache.size >= CACHE_MAX_SIZE) {
    const firstKey = embeddingCache.keys().next().value;
    embeddingCache.delete(firstKey);
  }
  
  embeddingCache.set(cacheKey, {
    embedding,
    timestamp: Date.now()
  });
};

// === CONTROLADORES PRINCIPALES ===

// 1. Subir y procesar documento
const uploadDocument = async (req, res) => {
  const startTime = Date.now();
  
  try {
    if (!req.file) {
      return res.status(400).json({
        success: false,
        error: {
          message: 'No se proporcionó ningún archivo',
          status: 400
        }
      });
    }
    
    const { file } = req;
    const { title, subject, author, tags, difficulty, type, userId } = req.body;
    
    logger.info('Procesando documento subido', {
      filename: file.originalname,
      size: file.size,
      mimetype: file.mimetype
    });
    
    // Extraer texto del archivo
    const fileExtension = path.extname(file.originalname).toLowerCase().slice(1);
    const extractedText = await extractTextFromFile(file.path, fileExtension);
    
    if (!extractedText || extractedText.length < parseInt(process.env.MIN_TEXT_LENGTH || '50')) {
      return res.status(400).json({
        success: false,
        error: {
          message: 'El documento no contiene suficiente texto para procesar',
          minLength: process.env.MIN_TEXT_LENGTH || 50,
          extractedLength: extractedText?.length || 0
        }
      });
    }
    
    // Preprocesar texto
    const cleanText = preprocessText(extractedText);
    
    // Dividir en chunks
    const chunkSize = parseInt(process.env.MAX_CHUNK_SIZE || '1000');
    const overlap = parseInt(process.env.CHUNK_OVERLAP || '200');
    const chunks = chunkText(cleanText, chunkSize, overlap);
    
    logger.info(`Documento dividido en ${chunks.length} chunks`);
    
    // Generar embeddings para cada chunk
    const documentEmbeddings = [];
    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      
      // Verificar cache
      let embedding = getCachedEmbedding(chunk.text);
      
      if (!embedding) {
        embedding = await embeddingProvider.generateEmbedding(chunk.text);
        setCachedEmbedding(chunk.text, embedding);
      }
      
      documentEmbeddings.push({
        chunkIndex: i,
        text: chunk.text,
        embedding: embedding,
        startIndex: chunk.startIndex,
        endIndex: chunk.endIndex
      });
    }
    
    // Crear documento en la base de datos
    const documentData = {
      id: uuidv4(),
      title: title || file.originalname,
      originalFilename: file.originalname,
      filePath: file.path,
      fileType: fileExtension,
      fileSize: file.size,
      subject: subject,
      author: author,
      tags: tags ? tags.split(',').map(tag => tag.trim()) : [],
      difficulty: difficulty || 'medium',
      type: type || 'notes',
      userId: userId,
      extractedText: cleanText,
      chunks: documentEmbeddings,
      embeddingModel: process.env.EMBEDDING_MODEL,
      createdAt: new Date().toISOString(),
      processedAt: new Date().toISOString()
    };
    
    // Guardar en la base de datos vectorial
    await embeddingProvider.storeDocument(documentData);
    
    const processingTime = Date.now() - startTime;
    updateStats('document_upload', processingTime, { fileType: fileExtension });
    
    logger.info('Documento procesado exitosamente', {
      documentId: documentData.id,
      chunks: chunks.length,
      processingTime: processingTime
    });
    
    res.json({
      success: true,
      data: {
        documentId: documentData.id,
        title: documentData.title,
        chunks: chunks.length,
        embeddings: documentEmbeddings.length,
        fileType: fileExtension,
        fileSize: file.size,
        metadata: {
          subject,
          author,
          tags: documentData.tags,
          difficulty,
          type,
          processingTime: processingTime,
          embeddingModel: process.env.EMBEDDING_MODEL
        }
      }
    });
    
  } catch (error) {
    const processingTime = Date.now() - startTime;
    
    logger.error('Error procesando documento', {
      error: error.message,
      stack: error.stack,
      processingTime: processingTime
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error procesando el documento',
        details: error.message,
        status: 500
      }
    });
  }
};

// 2. Procesar texto directo
const processText = async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { text, metadata, userId, chunkSize } = req.validatedBody;
    
    logger.info('Procesando texto directo', {
      textLength: text.length,
      userId: userId
    });
    
    // Preprocesar texto
    const cleanText = preprocessText(text);
    
    // Dividir en chunks si es necesario
    const actualChunkSize = chunkSize || parseInt(process.env.MAX_CHUNK_SIZE || '1000');
    const chunks = chunkText(cleanText, actualChunkSize);
    
    // Generar embeddings
    const textEmbeddings = [];
    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      
      let embedding = getCachedEmbedding(chunk.text);
      
      if (!embedding) {
        embedding = await embeddingProvider.generateEmbedding(chunk.text);
        setCachedEmbedding(chunk.text, embedding);
      }
      
      textEmbeddings.push({
        chunkIndex: i,
        text: chunk.text,
        embedding: embedding,
        startIndex: chunk.startIndex,
        endIndex: chunk.endIndex
      });
    }
    
    // Crear documento de texto
    const documentData = {
      id: uuidv4(),
      title: metadata?.title || 'Texto directo',
      originalFilename: null,
      filePath: null,
      fileType: 'direct_text',
      fileSize: text.length,
      subject: metadata?.subject,
      author: metadata?.author,
      tags: metadata?.tags || [],
      difficulty: metadata?.difficulty || 'medium',
      type: metadata?.type || 'notes',
      userId: userId,
      extractedText: cleanText,
      chunks: textEmbeddings,
      embeddingModel: process.env.EMBEDDING_MODEL,
      createdAt: new Date().toISOString(),
      processedAt: new Date().toISOString()
    };
    
    // Guardar en la base de datos vectorial
    await embeddingProvider.storeDocument(documentData);
    
    const processingTime = Date.now() - startTime;
    updateStats('document_upload', processingTime, { fileType: 'direct_text' });
    updateStats('embedding_generation', processingTime);
    
    res.json({
      success: true,
      data: {
        documentId: documentData.id,
        title: documentData.title,
        chunks: chunks.length,
        embeddings: textEmbeddings.length,
        metadata: {
          ...metadata,
          processingTime: processingTime,
          embeddingModel: process.env.EMBEDDING_MODEL
        }
      }
    });
    
  } catch (error) {
    const processingTime = Date.now() - startTime;
    
    logger.error('Error procesando texto directo', {
      error: error.message,
      processingTime: processingTime
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error procesando el texto',
        details: error.message,
        status: 500
      }
    });
  }
};

// 3. Búsqueda semántica
const semanticSearch = async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { query, limit, threshold, filters, includeMetadata } = req.validatedBody;
    
    logger.info('Realizando búsqueda semántica', {
      query: query.substring(0, 100),
      limit: limit,
      threshold: threshold,
      filters: filters
    });
    
    // Generar embedding de la consulta
    const queryEmbedding = await embeddingProvider.generateEmbedding(query);
    
    // Realizar búsqueda vectorial
    const searchResults = await embeddingProvider.searchSimilar({
      embedding: queryEmbedding,
      limit: limit || 10,
      threshold: threshold || parseFloat(process.env.SIMILARITY_THRESHOLD || '0.75'),
      filters: filters
    });
    
    const processingTime = Date.now() - startTime;
    updateStats('semantic_search', processingTime);
    
    // Formatear resultados
    const formattedResults = searchResults.map(result => ({
      documentId: result.documentId,
      chunkIndex: result.chunkIndex,
      text: result.text,
      similarity: result.similarity,
      ...(includeMetadata !== false && {
        metadata: {
          title: result.title,
          subject: result.subject,
          author: result.author,
          tags: result.tags,
          difficulty: result.difficulty,
          type: result.type,
          createdAt: result.createdAt
        }
      })
    }));
    
    logger.info('Búsqueda semántica completada', {
      resultsFound: formattedResults.length,
      processingTime: processingTime,
      averageSimilarity: formattedResults.length > 0 
        ? formattedResults.reduce((sum, r) => sum + r.similarity, 0) / formattedResults.length 
        : 0
    });
    
    res.json({
      success: true,
      data: {
        query: query,
        results: formattedResults,
        metadata: {
          totalResults: formattedResults.length,
          processingTime: processingTime,
          threshold: threshold || parseFloat(process.env.SIMILARITY_THRESHOLD || '0.75'),
          embeddingModel: process.env.EMBEDDING_MODEL,
          searchedAt: new Date().toISOString()
        }
      }
    });
    
  } catch (error) {
    const processingTime = Date.now() - startTime;
    
    logger.error('Error en búsqueda semántica', {
      error: error.message,
      query: req.validatedBody?.query?.substring(0, 100),
      processingTime: processingTime
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error en búsqueda semántica',
        details: error.message,
        status: 500
      }
    });
  }
};

// 4. Generar embeddings en lote
const batchEmbeddings = async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { texts, metadata, userId } = req.validatedBody;
    
    logger.info('Generando embeddings en lote', {
      textCount: texts.length,
      userId: userId
    });
    
    const batchResults = [];
    
    for (let i = 0; i < texts.length; i++) {
      const text = texts[i];
      const textMetadata = metadata && metadata[i] ? metadata[i] : {};
      
      try {
        // Verificar cache
        let embedding = getCachedEmbedding(text);
        
        if (!embedding) {
          embedding = await embeddingProvider.generateEmbedding(text);
          setCachedEmbedding(text, embedding);
        }
        
        batchResults.push({
          index: i,
          text: text,
          embedding: embedding,
          metadata: textMetadata,
          success: true
        });
        
      } catch (error) {
        logger.warn(`Error procesando texto ${i}`, { error: error.message });
        batchResults.push({
          index: i,
          text: text.substring(0, 100),
          error: error.message,
          success: false
        });
      }
    }
    
    const successCount = batchResults.filter(r => r.success).length;
    const processingTime = Date.now() - startTime;
    
    updateStats('embedding_generation', processingTime);
    
    logger.info('Embeddings en lote completados', {
      total: texts.length,
      successful: successCount,
      failed: texts.length - successCount,
      processingTime: processingTime
    });
    
    res.json({
      success: true,
      data: {
        results: batchResults,
        summary: {
          total: texts.length,
          successful: successCount,
          failed: texts.length - successCount,
          processingTime: processingTime,
          embeddingModel: process.env.EMBEDDING_MODEL
        }
      }
    });
    
  } catch (error) {
    const processingTime = Date.now() - startTime;
    
    logger.error('Error en embeddings en lote', {
      error: error.message,
      processingTime: processingTime
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error generando embeddings en lote',
        details: error.message,
        status: 500
      }
    });
  }
};

// 5. Obtener documentos con paginación
const getDocuments = async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 20;
    const filters = {
      subject: req.query.subject,
      author: req.query.author,
      type: req.query.type,
      difficulty: req.query.difficulty,
      userId: req.query.userId
    };
    
    // Filtrar valores undefined
    Object.keys(filters).forEach(key => {
      if (filters[key] === undefined) delete filters[key];
    });
    
    const documents = await embeddingProvider.getDocuments({
      page,
      limit,
      filters
    });
    
    res.json({
      success: true,
      data: {
        documents: documents.items,
        pagination: {
          page: page,
          limit: limit,
          total: documents.total,
          pages: Math.ceil(documents.total / limit)
        },
        filters: filters
      }
    });
    
  } catch (error) {
    logger.error('Error obteniendo documentos', { error: error.message });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error obteniendo documentos',
        details: error.message,
        status: 500
      }
    });
  }
};

// 6. Obtener documento específico
const getDocument = async (req, res) => {
  try {
    const { id } = req.params;
    const includeChunks = req.query.includeChunks === 'true';
    
    const document = await embeddingProvider.getDocument(id, { includeChunks });
    
    if (!document) {
      return res.status(404).json({
        success: false,
        error: {
          message: 'Documento no encontrado',
          documentId: id,
          status: 404
        }
      });
    }
    
    res.json({
      success: true,
      data: {
        document: document
      }
    });
    
  } catch (error) {
    logger.error('Error obteniendo documento', { 
      documentId: req.params.id,
      error: error.message 
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error obteniendo documento',
        details: error.message,
        status: 500
      }
    });
  }
};

// 7. Eliminar documento
const deleteDocument = async (req, res) => {
  try {
    const { id } = req.params;
    
    const deleted = await embeddingProvider.deleteDocument(id);
    
    if (!deleted) {
      return res.status(404).json({
        success: false,
        error: {
          message: 'Documento no encontrado',
          documentId: id,
          status: 404
        }
      });
    }
    
    logger.info('Documento eliminado', { documentId: id });
    
    res.json({
      success: true,
      data: {
        message: 'Documento eliminado correctamente',
        documentId: id
      }
    });
    
  } catch (error) {
    logger.error('Error eliminando documento', { 
      documentId: req.params.id,
      error: error.message 
    });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error eliminando documento',
        details: error.message,
        status: 500
      }
    });
  }
};

// === FUNCIONES EDUCATIVAS ESPECIALIZADAS ===

// 8. Encontrar contenido para exámenes
const findExamContent = async (req, res) => {
  const startTime = Date.now();
  
  try {
    const { subject, topics, difficulty, examType, limit } = req.body;
    
    logger.info('Buscando contenido para examen', {
      subject,
      topics: topics?.length || 0,
      difficulty,
      examType
    });
    
    // Construir consulta específica para exámenes
    const examQuery = `Contenido para examen de ${subject}. Temas: ${topics?.join(', ') || 'general'}. Nivel: ${difficulty || 'medio'}`;
    
    const queryEmbedding = await embeddingProvider.generateEmbedding(examQuery);
    
    const searchResults = await embeddingProvider.searchSimilar({
      embedding: queryEmbedding,
      limit: limit || 15,
      threshold: 0.7, // Umbral más bajo para exámenes
      filters: {
        subject: subject,
        difficulty: difficulty,
        type: ['notes', 'summary', 'exercise'] // Tipos relevantes para exámenes
      }
    });
    
    const processingTime = Date.now() - startTime;
    
    res.json({
      success: true,
      data: {
        examContent: searchResults,
        examContext: {
          subject,
          topics,
          difficulty,
          examType,
          contentPieces: searchResults.length,
          processingTime: processingTime
        }
      }
    });
    
  } catch (error) {
    logger.error('Error buscando contenido para examen', { error: error.message });
    
    res.status(500).json({
      success: false,
      error: {
        message: 'Error buscando contenido para examen',
        details: error.message,
        status: 500
      }
    });
  }
};

// === ESTADÍSTICAS Y UTILIDADES ===

// 9. Obtener estadísticas de uso
const getUsageStats = (req, res) => {
  const uptime = Date.now() - usageStats.startTime.getTime();
  
  res.json({
    success: true,
    data: {
      ...usageStats,
      uptime: uptime,
      cacheStats: {
        size: embeddingCache.size,
        maxSize: CACHE_MAX_SIZE,
        hitRate: '0%' // TODO: implementar tracking de cache hits
      },
      performance: {
        averageProcessingTime: Math.round(usageStats.averageProcessingTime),
        averageSearchTime: Math.round(usageStats.averageSearchTime)
      }
    }
  });
};

// 10. Limpiar cache
const clearCache = (req, res) => {
  embeddingCache.clear();
  
  logger.info('Cache de embeddings limpiado');
  
  res.json({
    success: true,
    data: {
      message: 'Cache limpiado correctamente',
      clearedEntries: embeddingCache.size
    }
  });
};

// === FUNCIONES PENDIENTES (stubs) ===

const uploadBatchDocuments = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const findSimilarDocuments = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const advancedSearch = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const updateDocument = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const getCollections = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const createCollection = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const getCollectionStats = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const generateEmbedding = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const checkEmbeddingQuality = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const reindexDocuments = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const getPerformanceMetrics = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const getStudySuggestions = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const analyzeKnowledgeGaps = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const testEmbeddings = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const compareTexts = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

const visualizeEmbeddings = async (req, res) => {
  res.status(501).json({ 
    success: false, 
    error: { message: 'Función en desarrollo', status: 501 } 
  });
};

module.exports = {
  // Gestión de documentos
  uploadDocument,
  uploadBatchDocuments,
  processText,
  getDocuments,
  getDocument,
  updateDocument,
  deleteDocument,
  
  // Embeddings
  batchEmbeddings,
  generateEmbedding,
  checkEmbeddingQuality,
  
  // Búsqueda semántica
  semanticSearch,
  findSimilarDocuments,
  advancedSearch,
  
  // Colecciones
  getCollections,
  createCollection,
  getCollectionStats,
  
  // Funciones educativas
  findExamContent,
  getStudySuggestions,
  analyzeKnowledgeGaps,
  
  // Mantenimiento
  reindexDocuments,
  clearCache,
  
  // Estadísticas
  getUsageStats,
  getPerformanceMetrics,
  
  // Debug (desarrollo)
  testEmbeddings,
  compareTexts,
  visualizeEmbeddings
};