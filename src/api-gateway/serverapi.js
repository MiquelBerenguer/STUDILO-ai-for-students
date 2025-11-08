const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');
const RedisStore = require('rate-limit-redis').default || require('rate-limit-redis');
const Redis = require('ioredis');
const { createProxyMiddleware } = require('http-proxy-middleware');
const pino = require('pino');
require('dotenv').config();

// --- CONFIGURACIÓN DE LOGS PROFESIONAL (PINO) ---
const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  base: { service: 'api-gateway' },
  timestamp: pino.stdTimeFunctions.isoTime,
  // En desarrollo local puedes usar: 'node serverapi.js | pino-pretty' para verlo bonito.
  // En producción, este formato JSON es el ideal.
});

const app = express();
const PORT = process.env.PORT || 3000;

// --- MIDDLEWARE DE SEGURIDAD ---
app.use(helmet());
app.use(cors());

// --- CONFIGURACIÓN REDIS HA (SENTINEL) ---
const redisOptions = {
  sentinels: [
    {
      host: process.env.REDIS_SENTINEL_HOST || 'redis-sentinel',
      port: parseInt(process.env.REDIS_SENTINEL_PORT || '26379')
    }
  ],
  name: process.env.REDIS_MASTER_SET || 'tutormaster',
  password: process.env.REDIS_PASSWORD,
  sentinelPassword: process.env.REDIS_PASSWORD,
  retryStrategy: (times) => Math.min(times * 50, 2000),
};

// Cliente para Rate Limiting
const redisClient = new Redis(redisOptions);

redisClient.on('error', (err) => {
  logger.error({ err }, '❌ Error en conexión Redis');
});

redisClient.on('connect', () => {
  logger.info('✅ Conectado a Redis vía Sentinel');
});

// --- RATE LIMITING DISTRIBUIDO ---
const limiter = rateLimit({
  store: new RedisStore({
    sendCommand: (...args) => redisClient.call(...args),
  }),
  windowMs: 15 * 60 * 1000, // 15 minutos
  max: 100, // Límite de 100 peticiones por ventana
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => {
    logger.warn({ ip: req.ip }, 'Rate limit excedido');
    res.status(429).json({
      error: 'Demasiadas peticiones. Por favor, espera un momento.'
    });
  }
});

app.use(limiter);

// --- LOGGING DE PETICIONES ---
app.use((req, res, next) => {
  // Pino maneja objetos mejor que console.log
  logger.info({
    method: req.method,
    url: req.url,
    ip: req.ip
  }, 'Incoming request');
  next();
});

// --- HEALTH CHECK ---
app.get('/health', async (req, res) => {
  let redisStatus = 'down';
  try {
    if (redisClient.status === 'ready') {
      await redisClient.ping();
      redisStatus = 'up';
    }
  } catch (e) {
    logger.error({ err: e }, 'Health check failed for Redis');
  }

  const status = redisStatus === 'up' ? 200 : 503;
  res.status(status).json({
    status: redisStatus === 'up' ? 'healthy' : 'degraded',
    services: {
      gateway: 'up',
      redis: redisStatus
    },
    timestamp: new Date().toISOString()
  });
});

// --- RUTAS DE PROXY ---
const proxyOptions = {
  changeOrigin: true,
  logLevel: 'silent', // Silenciamos el logger interno del proxy para usar el nuestro
  onError: (err, req, res) => {
    logger.error({ err, target: req.url }, 'Error en Proxy');
    res.status(503).json({ error: 'Servicio no disponible temporalmente' });
  }
};

app.use('/api/v1/auth', createProxyMiddleware({
  ...proxyOptions,
  target: process.env.AUTH_SERVICE_URL || 'http://auth-service:3001',
  pathRewrite: {
    '^/api/v1/auth': '',
  },
}));

app.use('/api/v1/documents', createProxyMiddleware({
  ...proxyOptions,
  target: process.env.PROCESSOR_SERVICE_URL || 'http://processor:8002',
  pathRewrite: {
    '^/api/v1/documents': '',
  },
}));

// --- MANEJO DE ERRORES ---
app.use('*', (req, res) => {
  logger.warn({ path: req.originalUrl }, 'Ruta no encontrada');
  res.status(404).json({ error: 'Endpoint no encontrado' });
});

// --- INICIO DEL SERVIDOR ---
app.listen(PORT, () => {
  logger.info({ port: PORT }, '🚀 API Gateway iniciado');
});

// Manejo grácil de cierre
process.on('SIGTERM', async () => {
  logger.info('SIGTERM recibido. Cerrando...');
  await redisClient.quit();
  process.exit(0);
});