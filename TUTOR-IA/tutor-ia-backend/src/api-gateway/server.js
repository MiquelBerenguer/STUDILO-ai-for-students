const express = require('express');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const Joi = require('joi');
const helmet = require('helmet');
const cors = require('cors');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());

// Simulación de base de datos (después conectaremos PostgreSQL)
let users = [];

// Esquemas de validación con Joi
const registerSchema = Joi.object({
  name: Joi.string().min(2).max(50).required(),
  email: Joi.string().email().required(),
  password: Joi.string().min(6).required()
});

const loginSchema = Joi.object({
  email: Joi.string().email().required(),
  password: Joi.string().required()
});

// JWT Secret (temporal - después irá en .env)
const JWT_SECRET = process.env.JWT_SECRET || 'mi-secreto-temporal-123';

// RUTAS DE AUTENTICACIÓN

// Registro de usuario
app.post('/auth/register', async (req, res) => {
  try {
    // 1. Validar datos de entrada
    const { error, value } = registerSchema.validate(req.body);
    if (error) {
      return res.status(400).json({
        error: 'Datos inválidos',
        details: error.details[0].message
      });
    }

    const { name, email, password } = value;

    // 2. Verificar si el email ya existe
    const existingUser = users.find(user => user.email === email);
    if (existingUser) {
      return res.status(409).json({
        error: 'El email ya está registrado'
      });
    }

    // 3. Encriptar contraseña
    const saltRounds = 10;
    const hashedPassword = await bcrypt.hash(password, saltRounds);

    // 4. Crear usuario
    const newUser = {
      id: users.length + 1,
      name,
      email,
      password: hashedPassword,
      createdAt: new Date().toISOString()
    };

    users.push(newUser);

    // 5. Responder (sin enviar la contraseña)
    res.status(201).json({
      message: 'Usuario registrado exitosamente',
      user: {
        id: newUser.id,
        name: newUser.name,
        email: newUser.email,
        createdAt: newUser.createdAt
      }
    });

  } catch (error) {
    console.error('Error en registro:', error);
    res.status(500).json({
      error: 'Error interno del servidor'
    });
  }
});

// Login de usuario
app.post('/auth/login', async (req, res) => {
  try {
    // 1. Validar datos de entrada
    const { error, value } = loginSchema.validate(req.body);
    if (error) {
      return res.status(400).json({
        error: 'Datos inválidos',
        details: error.details[0].message
      });
    }

    const { email, password } = value;

    // 2. Buscar usuario
    const user = users.find(u => u.email === email);
    if (!user) {
      return res.status(401).json({
        error: 'Email o contraseña incorrectos'
      });
    }

    // 3. Verificar contraseña
    const passwordMatch = await bcrypt.compare(password, user.password);
    if (!passwordMatch) {
      return res.status(401).json({
        error: 'Email o contraseña incorrectos'
      });
    }

    // 4. Generar token JWT
    const token = jwt.sign(
      { 
        userId: user.id, 
        email: user.email 
      },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    // 5. Responder con token
    res.json({
      message: 'Login exitoso',
      token: token,
      user: {
        id: user.id,
        name: user.name,
        email: user.email
      }
    });

  } catch (error) {
    console.error('Error en login:', error);
    res.status(500).json({
      error: 'Error interno del servidor'
    });
  }
});

// Verificar token
app.get('/auth/verify', (req, res) => {
  try {
    const token = req.headers.authorization?.replace('Bearer ', '');
    
    if (!token) {
      return res.status(401).json({
        error: 'Token no proporcionado'
      });
    }

    const decoded = jwt.verify(token, JWT_SECRET);
    
    res.json({
      valid: true,
      user: {
        userId: decoded.userId,
        email: decoded.email
      }
    });

  } catch (error) {
    res.status(401).json({
      valid: false,
      error: 'Token inválido'
    });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'auth-service',
    timestamp: new Date().toISOString(),
    users: users.length
  });
});

// Ruta raíz
app.get('/', (req, res) => {
  res.json({
    message: 'Tutor IA - Auth Service',
    version: '1.0.0',
    endpoints: [
      'POST /auth/register',
      'POST /auth/login', 
      'GET /auth/verify',
      'GET /health'
    ]
  });
});

app.listen(PORT, () => {
  console.log(`🔐 Auth Service corriendo en puerto ${PORT}`);
  console.log(`📋 Health check: http://localhost:${PORT}/health`);
});