const OpenAI = require('openai');
const winston = require('winston');
const fs = require('fs').promises;
const path = require('path');
const Database = require('better-sqlite3');

// Configurar logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'embedding-provider' },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

class EmbeddingProvider {
  constructor() {
    // Cliente OpenAI para embeddings
    this.openai = null;
    
    // Base de datos SQLite para metadatos y vectores
    this.db = null;
    
    // Configuración
    this.embeddingModel = process.env.EMBEDDING_MODEL || 'text-embedding-ada-002';
    this.embeddingDimensions = parseInt(process.env.EMBEDDING_DIMENSIONS) || 1536;
    this.vectorDbType = process.env.VECTOR_DB_TYPE || 'local';
    
    // Estado del proveedor
    this.isInitialized = false;
    this.health = {
      openai: false,
      database: false,
      lastCheck: null
    };
    
    // Inicializar
    this.initialize();
  }

  // === INICIALIZACIÓN ===
  
  async initialize() {
    try {
      logger.info('Inicializando EmbeddingProvider...');
      
      // Inicializar OpenAI
      await this.initializeOpenAI();
      
      // Inicializar base de datos
      await this.initializeDatabase();
      
      // Verificar salud
      await this.checkHealth();
      
      this.isInitialized = true;
      logger.info('✅ EmbeddingProvider inicializado correctamente');
      
    } catch (error) {
      logger.error('❌ Error inicializando EmbeddingProvider:', error.message);
      throw error;
    }
  }
  
  async initializeOpenAI() {
    try {
      if (!process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY === 'tu_clave_openai_aqui') {
        logger.warn('OpenAI API key no configurada - embeddings no funcionarán');
        return;
      }
      
      this.openai = new OpenAI({
        apiKey: process.env.OPENAI_API_KEY,
        timeout: 30000
      });
      
      // Test de conectividad
      await this.testOpenAIConnection();
      this.health.openai = true;
      
      logger.info('OpenAI client inicializado correctamente');
      
    } catch (error) {
      logger.error('Error inicializando OpenAI:', error.message);
      this.health.openai = false;
    }
  }
  
  async testOpenAIConnection() {
    if (!this.openai) return false;
    
    try {
      // Test con texto muy corto para minimizar costo
      const response = await this.openai.embeddings.create({
        model: this.embeddingModel,
        input: 'test'
      });
      
      return response.data && response.data.length > 0;
    } catch (error) {
      logger.warn('Test de conexión OpenAI falló:', error.message);
      return false;
    }
  }
  
  async initializeDatabase() {
    try {
      // Crear directorio de datos si no existe
      const dbPath = process.env.DATABASE_PATH || './data/vectordb.sqlite';
      const dbDir = path.dirname(dbPath);
      
      try {
        await fs.access(dbDir);
      } catch {
        await fs.mkdir(dbDir, { recursive: true });
      }
      
      // Inicializar SQLite
      this.db = new Database(dbPath);
      this.db.pragma('journal_mode = WAL'); // Mejor rendimiento
      
      // Crear tablas
      await this.createTables();
      
      this.health.database = true;
      logger.info(`Base de datos inicializada: ${dbPath}`);
      
    } catch (error) {
      logger.error('Error inicializando base de datos:', error.message);
      this.health.database = false;
      throw error;
    }
  }
  
  async createTables() {
    // Tabla de documentos
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        original_filename TEXT,
        file_path TEXT,
        file_type TEXT,
        file_size INTEGER,
        subject TEXT,
        author TEXT,
        tags TEXT, -- JSON array
        difficulty TEXT,
        type TEXT,
        user_id TEXT,
        extracted_text TEXT,
        embedding_model TEXT,
        created_at TEXT,
        processed_at TEXT,
        updated_at TEXT
      )
    `);
    
    // Tabla de chunks y embeddings
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS document_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding BLOB NOT NULL, -- Vector embeddings en formato binario
        start_index INTEGER,
        end_index INTEGER,
        created_at TEXT,
        FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
      )
    `);
    
    // Índices para búsqueda eficiente
    this.db.exec(`
      CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
      CREATE INDEX IF NOT EXISTS idx_documents_subject ON documents(subject);
      CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(type);
      CREATE INDEX IF NOT EXISTS idx_documents_difficulty ON documents(difficulty);
      CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
    `);
    
    // Tabla de colecciones (para organización)
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS collections (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at TEXT,
        updated_at TEXT
      )
    `);
    
    // Tabla de metadatos del sistema
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS system_metadata (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
      )
    `);
    
    // Insertar metadatos iniciales
    const insertMetadata = this.db.prepare(`
      INSERT OR REPLACE INTO system_metadata (key, value, updated_at) 
      VALUES (?, ?, ?)
    `);
    
    const now = new Date().toISOString();
    insertMetadata.run('embedding_model', this.embeddingModel, now);
    insertMetadata.run('embedding_dimensions', this.embeddingDimensions.toString(), now);
    insertMetadata.run('vector_db_type', this.vectorDbType, now);
    insertMetadata.run('initialized_at', now, now);
    
    logger.info('Tablas de base de datos creadas/verificadas');
  }

  // === GENERACIÓN DE EMBEDDINGS ===
  
  async generateEmbedding(text) {
    if (!this.openai) {
      throw new Error('OpenAI client no inicializado');
    }
    
    if (!text || text.trim().length === 0) {
      throw new Error('Texto vacío para embedding');
    }
    
    try {
      const startTime = Date.now();
      
      const response = await this.openai.embeddings.create({
        model: this.embeddingModel,
        input: text.trim()
      });
      
      const responseTime = Date.now() - startTime;
      
      if (!response.data || response.data.length === 0) {
        throw new Error('Respuesta de embedding vacía');
      }
      
      const embedding = response.data[0].embedding;
      
      if (process.env.LOG_EMBEDDINGS === 'true') {
        logger.info('Embedding generado', {
          textLength: text.length,
          embeddingDimensions: embedding.length,
          model: this.embeddingModel,
          responseTime: responseTime,
          tokensUsed: response.usage?.total_tokens || 0
        });
      }
      
      return embedding;
      
    } catch (error) {
      logger.error('Error generando embedding:', {
        error: error.message,
        textLength: text.length,
        model: this.embeddingModel
      });
      throw error;
    }
  }
  
  async generateBatchEmbeddings(texts) {
    if (!this.openai) {
      throw new Error('OpenAI client no inicializado');
    }
    
    if (!Array.isArray(texts) || texts.length === 0) {
      throw new Error('Array de textos vacío');
    }
    
    try {
      const startTime = Date.now();
      
      // OpenAI soporta hasta 2048 inputs por batch
      const batchSize = Math.min(texts.length, 100); // Limitamos a 100 para ser conservadores
      const batches = [];
      
      for (let i = 0; i < texts.length; i += batchSize) {
        batches.push(texts.slice(i, i + batchSize));
      }
      
      const allEmbeddings = [];
      
      for (const batch of batches) {
        const response = await this.openai.embeddings.create({
          model: this.embeddingModel,
          input: batch.map(text => text.trim())
        });
        
        allEmbeddings.push(...response.data.map(item => item.embedding));
      }
      
      const responseTime = Date.now() - startTime;
      
      logger.info('Batch embeddings generados', {
        totalTexts: texts.length,
        batches: batches.length,
        responseTime: responseTime
      });
      
      return allEmbeddings;
      
    } catch (error) {
      logger.error('Error generando batch embeddings:', error.message);
      throw error;
    }
  }

  // === ALMACENAMIENTO ===
  
  async storeDocument(documentData) {
    if (!this.db) {
      throw new Error('Base de datos no inicializada');
    }
    
    try {
      const transaction = this.db.transaction((doc) => {
        // Insertar documento
        const insertDoc = this.db.prepare(`
          INSERT OR REPLACE INTO documents (
            id, title, original_filename, file_path, file_type, file_size,
            subject, author, tags, difficulty, type, user_id, extracted_text,
            embedding_model, created_at, processed_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `);
        
        const now = new Date().toISOString();
        insertDoc.run(
          doc.id,
          doc.title,
          doc.originalFilename,
          doc.filePath,
          doc.fileType,
          doc.fileSize,
          doc.subject,
          doc.author,
          JSON.stringify(doc.tags || []),
          doc.difficulty,
          doc.type,
          doc.userId,
          doc.extractedText,
          doc.embeddingModel,
          doc.createdAt,
          doc.processedAt,
          now
        );
        
        // Insertar chunks con embeddings
        const insertChunk = this.db.prepare(`
          INSERT INTO document_chunks (
            document_id, chunk_index, text, embedding, start_index, end_index, created_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?)
        `);
        
        for (const chunk of doc.chunks) {
          // Convertir embedding array a Buffer para almacenamiento binario
          const embeddingBuffer = Buffer.from(new Float32Array(chunk.embedding).buffer);
          
          insertChunk.run(
            doc.id,
            chunk.chunkIndex,
            chunk.text,
            embeddingBuffer,
            chunk.startIndex,
            chunk.endIndex,
            now
          );
        }
      });
      
      transaction(documentData);
      
      logger.info('Documento almacenado', {
        documentId: documentData.id,
        chunks: documentData.chunks.length,
        title: documentData.title
      });
      
      return documentData.id;
      
    } catch (error) {
      logger.error('Error almacenando documento:', {
        error: error.message,
        documentId: documentData.id
      });
      throw error;
    }
  }

  // === BÚSQUEDA VECTORIAL ===
  
  async searchSimilar(options) {
    const {
      embedding,
      limit = 10,
      threshold = 0.75,
      filters = {}
    } = options;
    
    if (!this.db) {
      throw new Error('Base de datos no inicializada');
    }
    
    if (!embedding || !Array.isArray(embedding)) {
      throw new Error('Embedding inválido para búsqueda');
    }
    
    try {
      const startTime = Date.now();
      
      // Construir query con filtros
      let whereClause = '';
      const params = [];
      
      if (Object.keys(filters).length > 0) {
        const conditions = [];
        
        if (filters.subject) {
          conditions.push('d.subject = ?');
          params.push(filters.subject);
        }
        
        if (filters.difficulty) {
          conditions.push('d.difficulty = ?');
          params.push(filters.difficulty);
        }
        
        if (filters.type) {
          if (Array.isArray(filters.type)) {
            conditions.push(`d.type IN (${filters.type.map(() => '?').join(',')})`);
            params.push(...filters.type);
          } else {
            conditions.push('d.type = ?');
            params.push(filters.type);
          }
        }
        
        if (filters.author) {
          conditions.push('d.author = ?');
          params.push(filters.author);
        }
        
        if (filters.userId) {
          conditions.push('d.user_id = ?');
          params.push(filters.userId);
        }
        
        if (conditions.length > 0) {
          whereClause = 'WHERE ' + conditions.join(' AND ');
        }
      }
      
      // Query para obtener todos los chunks con metadatos
      const query = `
        SELECT 
          c.document_id,
          c.chunk_index,
          c.text,
          c.embedding,
          c.start_index,
          c.end_index,
          d.title,
          d.subject,
          d.author,
          d.tags,
          d.difficulty,
          d.type,
          d.created_at
        FROM document_chunks c
        JOIN documents d ON c.document_id = d.id
        ${whereClause}
        ORDER BY c.document_id, c.chunk_index
      `;
      
      const rows = this.db.prepare(query).all(...params);
      
      // Calcular similitudes
      const results = [];
      
      for (const row of rows) {
        // Convertir embedding de Buffer a array
        const storedEmbedding = new Float32Array(row.embedding.buffer);
        
        // Calcular similitud coseno
        const similarity = this.cosineSimilarity(embedding, Array.from(storedEmbedding));
        
        if (similarity >= threshold) {
          results.push({
            documentId: row.document_id,
            chunkIndex: row.chunk_index,
            text: row.text,
            similarity: similarity,
            startIndex: row.start_index,
            endIndex: row.end_index,
            title: row.title,
            subject: row.subject,
            author: row.author,
            tags: JSON.parse(row.tags || '[]'),
            difficulty: row.difficulty,
            type: row.type,
            createdAt: row.created_at
          });
        }
      }
      
      // Ordenar por similitud descendente y limitar resultados
      results.sort((a, b) => b.similarity - a.similarity);
      const limitedResults = results.slice(0, limit);
      
      const searchTime = Date.now() - startTime;
      
      if (process.env.LOG_SEARCH_QUERIES === 'true') {
        logger.info('Búsqueda vectorial completada', {
          totalChunks: rows.length,
          resultsFound: limitedResults.length,
          threshold: threshold,
          searchTime: searchTime,
          averageSimilarity: limitedResults.length > 0 
            ? limitedResults.reduce((sum, r) => sum + r.similarity, 0) / limitedResults.length 
            : 0
        });
      }
      
      return limitedResults;
      
    } catch (error) {
      logger.error('Error en búsqueda vectorial:', error.message);
      throw error;
    }
  }
  
  // Calcular similitud coseno entre dos vectores
  cosineSimilarity(vecA, vecB) {
    if (vecA.length !== vecB.length) {
      throw new Error('Los vectores deben tener la misma dimensión');
    }
    
    let dotProduct = 0;
    let normA = 0;
    let normB = 0;
    
    for (let i = 0; i < vecA.length; i++) {
      dotProduct += vecA[i] * vecB[i];
      normA += vecA[i] * vecA[i];
      normB += vecB[i] * vecB[i];
    }
    
    if (normA === 0 || normB === 0) {
      return 0;
    }
    
    return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
  }

  // === GESTIÓN DE DOCUMENTOS ===
  
  async getDocuments(options = {}) {
    const {
      page = 1,
      limit = 20,
      filters = {}
    } = options;
    
    if (!this.db) {
      throw new Error('Base de datos no inicializada');
    }
    
    try {
      // Construir WHERE clause
      let whereClause = '';
      const params = [];
      
      if (Object.keys(filters).length > 0) {
        const conditions = [];
        
        Object.keys(filters).forEach(key => {
          if (filters[key] !== undefined) {
            conditions.push(`${key} = ?`);
            params.push(filters[key]);
          }
        });
        
        if (conditions.length > 0) {
          whereClause = 'WHERE ' + conditions.join(' AND ');
        }
      }
      
      // Query para contar total
      const countQuery = `SELECT COUNT(*) as total FROM documents ${whereClause}`;
      const totalResult = this.db.prepare(countQuery).get(...params);
      const total = totalResult.total;
      
      // Query para obtener documentos paginados
      const offset = (page - 1) * limit;
      const documentsQuery = `
        SELECT 
          id, title, original_filename, file_type, file_size,
          subject, author, tags, difficulty, type, user_id,
          embedding_model, created_at, processed_at, updated_at
        FROM documents 
        ${whereClause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
      `;
      
      params.push(limit, offset);
      const documents = this.db.prepare(documentsQuery).all(...params);
      
      // Formatear resultados
      const formattedDocs = documents.map(doc => ({
        ...doc,
        tags: JSON.parse(doc.tags || '[]'),
        fileSize: this.formatFileSize(doc.file_size)
      }));
      
      return {
        items: formattedDocs,
        total: total,
        page: page,
        limit: limit
      };
      
    } catch (error) {
      logger.error('Error obteniendo documentos:', error.message);
      throw error;
    }
  }
  
  async getDocument(id, options = {}) {
    const { includeChunks = false } = options;
    
    if (!this.db) {
      throw new Error('Base de datos no inicializada');
    }
    
    try {
      // Obtener documento
      const docQuery = `
        SELECT * FROM documents WHERE id = ?
      `;
      const document = this.db.prepare(docQuery).get(id);
      
      if (!document) {
        return null;
      }
      
      // Formatear documento
      const formattedDoc = {
        ...document,
        tags: JSON.parse(document.tags || '[]'),
        fileSize: this.formatFileSize(document.file_size)
      };
      
      // Incluir chunks si se solicita
      if (includeChunks) {
        const chunksQuery = `
          SELECT chunk_index, text, start_index, end_index, created_at
          FROM document_chunks 
          WHERE document_id = ?
          ORDER BY chunk_index
        `;
        const chunks = this.db.prepare(chunksQuery).all(id);
        formattedDoc.chunks = chunks;
      }
      
      return formattedDoc;
      
    } catch (error) {
      logger.error('Error obteniendo documento:', {
        documentId: id,
        error: error.message
      });
      throw error;
    }
  }
  
  async deleteDocument(id) {
    if (!this.db) {
      throw new Error('Base de datos no inicializada');
    }
    
    try {
      const transaction = this.db.transaction((docId) => {
        // Eliminar chunks primero (por la foreign key)
        const deleteChunks = this.db.prepare('DELETE FROM document_chunks WHERE document_id = ?');
        const chunksResult = deleteChunks.run(docId);
        
        // Eliminar documento
        const deleteDoc = this.db.prepare('DELETE FROM documents WHERE id = ?');
        const docResult = deleteDoc.run(docId);
        
        return {
          documentsDeleted: docResult.changes,
          chunksDeleted: chunksResult.changes
        };
      });
      
      const result = transaction(id);
      
      if (result.documentsDeleted > 0) {
        logger.info('Documento eliminado', {
          documentId: id,
          chunksDeleted: result.chunksDeleted
        });
        return true;
      }
      
      return false;
      
    } catch (error) {
      logger.error('Error eliminando documento:', {
        documentId: id,
        error: error.message
      });
      throw error;
    }
  }

  // === UTILIDADES ===
  
  formatFileSize(bytes) {
    if (!bytes) return '0 B';
    
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  }
  
  async checkHealth() {
    this.health.lastCheck = new Date().toISOString();
    
    // Verificar OpenAI
    if (this.openai) {
      this.health.openai = await this.testOpenAIConnection();
    }
    
    // Verificar base de datos
    if (this.db) {
      try {
        this.db.prepare('SELECT 1').get();
        this.health.database = true;
      } catch {
        this.health.database = false;
      }
    }
    
    return this.health;
  }
  
  getHealth() {
    return {
      ...this.health,
      isInitialized: this.isInitialized,
      configuration: {
        embeddingModel: this.embeddingModel,
        embeddingDimensions: this.embeddingDimensions,
        vectorDbType: this.vectorDbType
      }
    };
  }
  
  // Cerrar conexiones
  close() {
    if (this.db) {
      this.db.close();
      logger.info('Base de datos cerrada');
    }
  }
}

module.exports = EmbeddingProvider;