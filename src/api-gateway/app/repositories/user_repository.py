from sqlalchemy.orm import Session
from typing import Optional
from src.shared.database.models import User
from app.core.security import get_password_hash
from app.schemas.user import UserCreate
import uuid

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()
    
    def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()
    
    def create(self, user_in: UserCreate) -> User:
        hashed_password = get_password_hash(user_in.password)
        
        db_user = User(
            email=user_in.email,
            hashed_password=hashed_password,
            full_name=user_in.full_name
        )
        
        try:
            self.db.add(db_user)
            self.db.commit()
            self.db.refresh(db_user)
            return db_user
        except Exception as e:
            self.db.rollback()
            raise e

    def update_password(self, email: str, new_hashed_password: str) -> Optional[User]:
       """
       Busca un usuario por email y actualiza su contraseña.
       """
       user = self.get_by_email(email)
       if user:
           user.hashed_password = new_hashed_password
           try:
               self.db.add(user)
               self.db.commit()
               self.db.refresh(user)
               return user
           except Exception as e:
               self.db.rollback()
               raise e
       return None