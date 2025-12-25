from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

# Configuración del contexto de hashing
# schemes=["bcrypt"]: Es robusto y lento por diseño (bueno contra fuerza bruta)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si la contraseña plana coincide con el hash guardado."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Convierte una contraseña plana en un hash seguro."""
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Genera un Token JWT stateless siguiendo estándares de seguridad.
    """
    # Usamos timezone.utc explícito para evitar problemas en servidores distribuidos
    now = datetime.now(timezone.utc)
    
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Payload enriquecido
    to_encode = {
        "exp": expire,          # Expiración
        "iat": now,             # Issued At: Cuándo se creó (vital para invalidación)
        "sub": str(subject),    # Subject: ID del usuario (aseguramos que sea string, ej. UUID)
        "type": "access"        # Evita confusión con Refresh Tokens futuros
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt