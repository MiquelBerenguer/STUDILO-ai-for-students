from pydantic import BaseModel, EmailStr, Field, validator, ConfigDict
from typing import Optional
import uuid

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, example="StrongPass123!")
    full_name: Optional[str] = None

    @validator('password')
    def password_complexity(cls, v):
        return v

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    
    # Configuración Pydantic v2
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str