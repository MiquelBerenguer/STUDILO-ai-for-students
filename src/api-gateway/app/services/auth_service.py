from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.core.security import verify_password, create_access_token
from datetime import timedelta
from app.core.config import settings

class AuthService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

    def register_user(self, user_in: UserCreate):
        # 1. Verificar si ya existe
        if self.user_repo.get_by_email(user_in.email):
            raise HTTPException(
                status_code=400,
                detail="El email ya está registrado."
            )
        # 2. Crear
        return self.user_repo.create(user_in)

    def login_user(self, email: str, password: str):
        # 1. Buscar usuario
        user = self.user_repo.get_by_email(email)
        
        # 2. Validar password (y evitar Timing Attacks respondiendo genérico)
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 3. Generar Token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=user.id,
            expires_delta=access_token_expires
        )
        
        return {"access_token": access_token, "token_type": "bearer"}