const Joi = require('joi');
const { v4: uuidv4 } = require('uuid');

/**
 * Modelo de Document para el Vector DB
 * Define la estructura, validaciones y métodos para documentos educativos
 */
class Document {
  constructor(data = {}) {
    this.id = data.id || uuidv4();
    this.title = data.title;
    this.originalFilename = data.originalFilename;
    this.filePath = data.filePath;
    this.fileType = data.fileType;
    this.fileSize = data.fileSize;
    this.subject = data.subject;
    this.author = data.author;
    this.tags = data.tags || [];
    this.difficulty = data.difficulty || 'medium';
    this.type = data.type || 'notes';
    this.userId = data.userId;
    this.extractedText = data.extractedText;
    this.chunks = data.chunks || [];
    this.embeddingModel = data.embeddingModel;
    this.createdAt = data.createdAt || new Date().toISOString();
    this.processedAt = data.processedAt;
    this.updatedAt = data.updatedAt;
  }

  // === ESQUEMAS DE VALIDACIÓN ===

  static get validationSchema() {
    return Joi.object({
      id: Joi.string().uuid().optional(),
      title: Joi.string().required().min(1).max(255).trim(),
      originalFilename: Joi.string().optional().allow(null),
      filePath: Joi.string().optional().allow(null),
      fileType: Joi.string().valid('pdf', 'txt', 'docx', 'md', 'direct_text').required(),
      fileSize: Joi.number().integer().min(0).optional(),
      subject: Joi.string().optional().max(100).trim(),
      author: Joi.string().optional().max(100).trim(),
      tags: Joi.array().items(Joi.string().trim()).optional().default([]),
      difficulty: Joi.string().valid('easy', 'medium', 'hard').optional().default('medium'),
      type: Joi.string().valid('notes', 'exam', 'summary', 'exercise', 'reference').optional().default('notes'),
      userId: Joi.string().optional().trim(),
      extractedText: Joi.string().required().min(10),
      chunks: Joi.array().items(Joi.object({
        chunkIndex: Joi.number().integer().min(0).required(),
        text: Joi.string().required().min(1),
        embedding: Joi.array().items(Joi.number()).required(),
        startIndex: Joi.number().integer().min(0).optional(),
        endIndex: Joi.number().integer().min(0).optional()
      })).optional().default([]),
      embeddingModel: Joi.string().optional(),
      createdAt: Joi.string().isoDate().optional(),
      processedAt: Joi.string().isoDate().optional(),
      updatedAt: Joi.string().isoDate().optional()
    });
  }

  static get updateSchema() {
    return Joi.object({
      title: Joi.string().min(1).max(255).trim().optional(),
      subject: Joi.string().max(100).trim().optional(),
      author: Joi.string().max(100).trim().optional(),
      tags: Joi.array().items(Joi.string().trim()).optional(),
      difficulty: Joi.string().valid('easy', 'medium', 'hard').optional(),
      type: Joi.string().valid('notes', 'exam', 'summary', 'exercise', 'reference').optional()
    });
  }

  // === MÉTODOS DE VALIDACIÓN ===

  validate() {
    const { error, value } = Document.validationSchema.validate(this.toObject(), {
      abortEarly: false,
      stripUnknown: true
    });

    if (error) {
      throw new ValidationError('Datos del documento inválidos', error.details);
    }

    return value;
  }

  static validateUpdate(updateData) {
    const { error, value } = Document.updateSchema.validate(updateData, {
      abortEarly: false,
      stripUnknown: true
    });

    if (error) {
      throw new ValidationError('Datos de actualización inválidos', error.details);
    }

    return value;
  }

  // === MÉTODOS DE TRANSFORMACIÓN ===

  toObject() {
    return {
      id: this.id,
      title: this.title,
      originalFilename: this.originalFilename,
      filePath: this.filePath,
      fileType: this.fileType,
      fileSize: this.fileSize,
      subject: this.subject,
      author: this.author,
      tags: this.tags,
      difficulty: this.difficulty,
      type: this.type,
      userId: this.userId,
      extractedText: this.extractedText,
      chunks: this.chunks,
      embeddingModel: this.embeddingModel,
      createdAt: this.createdAt,
      processedAt: this.processedAt,
      updatedAt: this.updatedAt
    };
  }

  toJSON() {
    return this.toObject();
  }

  // Versión pública (sin datos sensibles)
  toPublicObject() {
    return {
      id: this.id,
      title: this.title,
      originalFilename: this.originalFilename,
      fileType: this.fileType,
      fileSize: this.fileSize,
      subject: this.subject,
      author: this.author,
      tags: this.tags,
      difficulty: this.difficulty,
      type: this.type,
      embeddingModel: this.embeddingModel,
      createdAt: this.createdAt,
      processedAt: this.processedAt,
      updatedAt: this.updatedAt,
      // Metadatos calculados
      chunkCount: this.chunks.length,
      textLength: this.extractedText ? this.extractedText.length : 0,
      hasEmbeddings: this.chunks.length > 0 && this.chunks.every(c => c.embedding && c.embedding.length > 0)
    };
  }

  // === MÉTODOS DE UTILIDAD ===

  update(updateData) {
    const validatedData = Document.validateUpdate(updateData);
    
    Object.keys(validatedData).forEach(key => {
      if (validatedData[key] !== undefined) {
        this[key] = validatedData[key];
      }
    });

    this.updatedAt = new Date().toISOString();
    return this;
  }

  // Añadir chunk con embedding
  addChunk(chunkData) {
    const chunkSchema = Joi.object({
      text: Joi.string().required().min(1),
      embedding: Joi.array().items(Joi.number()).required(),
      startIndex: Joi.number().integer().min(0).optional(),
      endIndex: Joi.number().integer().min(0).optional()
    });

    const { error, value } = chunkSchema.validate(chunkData);
    if (error) {
      throw new ValidationError('Datos del chunk inválidos', error.details);
    }

    const chunk = {
      chunkIndex: this.chunks.length,
      text: value.text,
      embedding: value.embedding,
      startIndex: value.startIndex,
      endIndex: value.endIndex
    };

    this.chunks.push(chunk);
    return chunk;
  }

  // Obtener estadísticas del documento
  getStats() {
    return {
      id: this.id,
      title: this.title,
      chunkCount: this.chunks.length,
      textLength: this.extractedText ? this.extractedText.length : 0,
      averageChunkLength: this.chunks.length > 0 
        ? Math.round(this.chunks.reduce((sum, chunk) => sum + chunk.text.length, 0) / this.chunks.length)
        : 0,
      embeddingDimensions: this.chunks.length > 0 && this.chunks[0].embedding 
        ? this.chunks[0].embedding.length 
        : 0,
      fileSize: this.fileSize,
      subject: this.subject,
      difficulty: this.difficulty,
      type: this.type,
      createdAt: this.createdAt,
      processedAt: this.processedAt
    };
  }

  // Buscar texto en chunks
  searchInChunks(query, options = {}) {
    const { caseSensitive = false, exactMatch = false } = options;
    const searchQuery = caseSensitive ? query : query.toLowerCase();

    return this.chunks.filter(chunk => {
      const chunkText = caseSensitive ? chunk.text : chunk.text.toLowerCase();
      
      if (exactMatch) {
        return chunkText.includes(searchQuery);
      } else {
        // Búsqueda por palabras
        return searchQuery.split(' ').some(word => 
          chunkText.includes(word.trim())
        );
      }
    }).map(chunk => ({
      ...chunk,
      documentId: this.id,
      documentTitle: this.title
    }));
  }

  // === MÉTODOS ESTÁTICOS ===

  static fromDatabaseRow(row) {
    if (!row) return null;

    return new Document({
      id: row.id,
      title: row.title,
      originalFilename: row.original_filename,
      filePath: row.file_path,
      fileType: row.file_type,
      fileSize: row.file_size,
      subject: row.subject,
      author: row.author,
      tags: row.tags ? JSON.parse(row.tags) : [],
      difficulty: row.difficulty,
      type: row.type,
      userId: row.user_id,
      extractedText: row.extracted_text,
      embeddingModel: row.embedding_model,
      createdAt: row.created_at,
      processedAt: row.processed_at,
      updatedAt: row.updated_at
    });
  }

  toDatabaseRow() {
    return {
      id: this.id,
      title: this.title,
      original_filename: this.originalFilename,
      file_path: this.filePath,
      file_type: this.fileType,
      file_size: this.fileSize,
      subject: this.subject,
      author: this.author,
      tags: JSON.stringify(this.tags),
      difficulty: this.difficulty,
      type: this.type,
      user_id: this.userId,
      extracted_text: this.extractedText,
      embedding_model: this.embeddingModel,
      created_at: this.createdAt,
      processed_at: this.processedAt,
      updated_at: this.updatedAt
    };
  }

  // === CONSTANTES Y ENUMS ===

  static get FILE_TYPES() {
    return {
      PDF: 'pdf',
      TXT: 'txt',
      DOCX: 'docx',
      MD: 'md',
      DIRECT_TEXT: 'direct_text'
    };
  }

  static get DIFFICULTIES() {
    return {
      EASY: 'easy',
      MEDIUM: 'medium',
      HARD: 'hard'
    };
  }

  static get TYPES() {
    return {
      NOTES: 'notes',
      EXAM: 'exam',
      SUMMARY: 'summary',
      EXERCISE: 'exercise',
      REFERENCE: 'reference'
    };
  }

  static get ALLOWED_FILE_EXTENSIONS() {
    return ['pdf', 'txt', 'docx', 'md'];
  }

  // === MÉTODOS DE FACTORY ===

  static createFromUpload(fileData, metadata = {}) {
    return new Document({
      title: metadata.title || fileData.originalname,
      originalFilename: fileData.originalname,
      filePath: fileData.path,
      fileType: fileData.originalname.split('.').pop().toLowerCase(),
      fileSize: fileData.size,
      subject: metadata.subject,
      author: metadata.author,
      tags: metadata.tags ? metadata.tags.split(',').map(tag => tag.trim()) : [],
      difficulty: metadata.difficulty || 'medium',
      type: metadata.type || 'notes',
      userId: metadata.userId
    });
  }

  static createFromText(text, metadata = {}) {
    return new Document({
      title: metadata.title || 'Texto directo',
      fileType: 'direct_text',
      fileSize: text.length,
      extractedText: text,
      subject: metadata.subject,
      author: metadata.author,
      tags: metadata.tags || [],
      difficulty: metadata.difficulty || 'medium',
      type: metadata.type || 'notes',
      userId: metadata.userId
    });
  }
}

// === CLASE DE ERROR PERSONALIZADA ===

class ValidationError extends Error {
  constructor(message, details = []) {
    super(message);
    this.name = 'ValidationError';
    this.details = details;
    this.status = 400;
  }
}

// === FUNCIONES DE UTILIDAD ===

const DocumentUtils = {
  // Formatear tamaño de archivo
  formatFileSize(bytes) {
    if (!bytes) return '0 B';
    
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  },

  // Validar extensión de archivo
  isValidFileExtension(filename) {
    const extension = filename.split('.').pop().toLowerCase();
    return Document.ALLOWED_FILE_EXTENSIONS.includes(extension);
  },

  // Obtener tipo de contenido por extensión
  getContentType(fileType) {
    const contentTypes = {
      pdf: 'application/pdf',
      txt: 'text/plain',
      docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      md: 'text/markdown'
    };
    
    return contentTypes[fileType] || 'application/octet-stream';
  },

  // Sanitizar nombre de archivo
  sanitizeFilename(filename) {
    return filename
      .replace(/[^a-zA-Z0-9.\-_]/g, '_')
      .replace(/_{2,}/g, '_')
      .substring(0, 255);
  },

  // Extraer metadatos de nombre de archivo
  extractMetadataFromFilename(filename) {
    const nameParts = filename.replace(/\.[^/.]+$/, '').split(/[-_\s]+/);
    
    // Intentar detectar patrones comunes
    const metadata = {
      subject: null,
      difficulty: null,
      type: null
    };

    // Buscar indicadores de dificultad
    const difficultyIndicators = {
      'facil': 'easy',
      'easy': 'easy',
      'medio': 'medium', 
      'medium': 'medium',
      'dificil': 'hard',
      'hard': 'hard',
      'avanzado': 'hard'
    };

    // Buscar indicadores de tipo
    const typeIndicators = {
      'apuntes': 'notes',
      'notes': 'notes',
      'examen': 'exam',
      'exam': 'exam',
      'resumen': 'summary',
      'summary': 'summary',
      'ejercicio': 'exercise',
      'exercise': 'exercise'
    };

    nameParts.forEach(part => {
      const lowerPart = part.toLowerCase();
      
      if (difficultyIndicators[lowerPart]) {
        metadata.difficulty = difficultyIndicators[lowerPart];
      }
      
      if (typeIndicators[lowerPart]) {
        metadata.type = typeIndicators[lowerPart];
      }
    });

    return metadata;
  }
};

module.exports = {
  Document,
  ValidationError,
  DocumentUtils
};