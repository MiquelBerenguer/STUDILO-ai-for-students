from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.base import utcnow
from app.db.models import AuthSession, User

COOKIE_NAME = "studilo_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    key = get_settings().APP_SECRET_KEY.get_secret_value().encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def create_session(db: Session, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user_id, token_hash=_token_hash(token),
                       expires_at=utcnow() + timedelta(days=get_settings().SESSION_TTL_DAYS)))
    return token


def resolve_session(db: Session, token: str) -> User | None:
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if row is None or row.expires_at < utcnow():
        return None
    return db.get(User, row.user_id)


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
