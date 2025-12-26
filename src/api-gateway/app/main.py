import logging
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware  # <--- IMPORTANTE: Importamos el Middleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

# --- Importaciones de Infraestructura y Config ---
from app.core.config import settings
from app.core.rabbitmq import mq_client
from src.shared.database.database import get_db
from src.shared.database.models import User 
from app.schemas.user import UserCreate, UserResponse, Token
from app.services.auth_service import AuthService

# --- Importaciones de Seguridad y Dependencias ---
from app.dependencies import get_current_user 
from app.core.security import verify_password, get_password_hash

# --- Importaciones de Rutas (Módulos) ---
from src.services.learning.api.routes import router as learning_router

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API-Gateway")

# --- Modelos de Datos Locales ---
class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=1, example="OldPass123!")
    new_password: str = Field(..., min_length=8, example="NewStrongPass123!")

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await mq_client.connect()
        logger.info("✅ RabbitMQ conectado exitosamente")
    except Exception as e:
        logger.error(f"⚠️ El Gateway arrancó sin RabbitMQ: {e}")
    yield
    await mq_client.close()
    logger.info("🛑 RabbitMQ desconectado")

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# =============================================================================
# 🌍 CONFIGURACIÓN CORS (CRÍTICO PARA FRONTEND)
# =============================================================================
# Define quién puede llamar a tu API. 
# ["*"] permite a TODO el mundo (ideal para desarrollo local).
# En producción, cámbialo por: ["https://tutor-ia.com", "http://localhost:3000"]
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],    # Permite GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],    # Permite headers como Authorization
)

# =============================================================================
# 🩺 HEALTH CHECK
# =============================================================================
@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "rabbitmq": "connected" if mq_client.connection and not mq_client.connection.is_closed else "disconnected"
    }

# =============================================================================
# 🔐 RUTAS DE AUTENTICACIÓN (CORE)
# =============================================================================

@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Crea un usuario nuevo."""
    auth_service = AuthService(db)
    return auth_service.register_user(user_in)

@app.post("/auth/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login que devuelve el JWT Token."""
    auth_service = AuthService(db)
    return auth_service.login_user(email=form_data.username, password=form_data.password)

@app.post("/auth/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Permite cambiar la contraseña verificando la anterior.
    """
    if not verify_password(request.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta."
        )

    if request.old_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser diferente."
        )

    auth_service = AuthService(db)
    new_hash = get_password_hash(request.new_password)
    
    updated_user = auth_service.user_repo.update_password(current_user.email, new_hash)
    
    if not updated_user:
        raise HTTPException(status_code=404, detail="Error actualizando usuario.")

    return {"message": "Contraseña actualizada correctamente."}

# =============================================================================
# 🔌 CONEXIÓN DE MÓDULOS (LEARNING CORE)
# =============================================================================

app.include_router(
    learning_router,
    prefix="/api/v1/learning",
    tags=["Learning Core"],
    dependencies=[Depends(get_current_user)] 
)