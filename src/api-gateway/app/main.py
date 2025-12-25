import time
import uuid
import logging
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from jose import jwt, JWTError

# --- Importaciones de nuestra Arquitectura ---
from app.core.config import settings
from app.core.rabbitmq import mq_client
from src.shared.database.database import get_db
from src.shared.database.models import User # Necesario para el tipado
from app.schemas.user import UserCreate, UserResponse, Token
from app.services.auth_service import AuthService

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API-Gateway")

# --- Seguridad: Configuración OAuth2 ---
# Indica a Swagger que el botón de "candadito" debe llamar a este endpoint para obtener el token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# --- Modelos de Datos ---
class ExamRequest(BaseModel):
    topic: str = Field(..., min_length=3, example="Termodinámica Aplicada")
    difficulty: str = Field(..., pattern="^(easy|medium|hard)$", example="hard")

class ExamResponse(BaseModel):
    task_id: str
    status: str
    message: str

# --- Dependencia de Autenticación (El Portero de la Discoteca) ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    1. Recibe el token del Header 'Authorization'.
    2. Lo decodifica usando la SECRET_KEY.
    3. Verifica que el usuario exista en la DB.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decodificamos el JWT
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Verificamos contra la DB usando el repositorio
    auth_service = AuthService(db)
    # CORRECCIÓN: Usamos 'user_repo' que es como lo definimos en el paso anterior
    user = auth_service.user_repo.get_by_id(user_id) 
    
    if user is None:
        raise credentials_exception
    return user

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await mq_client.connect()
    except Exception as e:
        logger.error(f"⚠️ El Gateway arrancó sin RabbitMQ: {e}")
    yield
    await mq_client.close()

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "rabbitmq": "connected" if mq_client.connection and not mq_client.connection.is_closed else "disconnected"}

# ==========================================
# 🔐 RUTAS DE AUTENTICACIÓN (Tarea 4.2)
# ==========================================

@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Crea un usuario nuevo (Captura email para marketing)."""
    auth_service = AuthService(db)
    return auth_service.register_user(user_in)

@app.post("/auth/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login que devuelve el JWT Token."""
    auth_service = AuthService(db)
    # Mapeamos form_data.username -> email
    return auth_service.login_user(email=form_data.username, password=form_data.password)

# ==========================================
# 🛡️ ENDPOINT PROTEGIDO (Tarea 4.1 + 4.2)
# ==========================================
@app.post("/exams/generate", status_code=status.HTTP_202_ACCEPTED, response_model=ExamResponse)
async def request_exam_generation(
    request: ExamRequest,
    # INYECCIÓN DE DEPENDENCIA: Aquí está la seguridad.
    # Si no envían token válido, se detiene aquí con Error 401.
    current_user: User = Depends(get_current_user) 
):
    """
    Solicitud de Examen (Solo usuarios registrados).
    """
    task_id = str(uuid.uuid4())
    
    # Payload enriquecido: ¡Ahora sabemos quién pide el examen!
    payload = {
        "task_id": task_id,
        "user_id": str(current_user.id), # <--- VITAL: Vinculamos examen a usuario
        "email": current_user.email,     # <--- VITAL: Para enviarle el resultado luego
        "action": "generate_exam",
        "topic": request.topic,
        "difficulty": request.difficulty,
        "created_at": time.time(),
        "origin": "api-gateway"
    }
    
    success = await mq_client.send_message(payload)
    
    if not success:
        raise HTTPException(status_code=503, detail="Sistema saturado")
        
    return {
        "task_id": task_id,
        "status": "queued", 
        "message": "Solicitud aceptada. Procesando..."
    }