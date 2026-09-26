"""Encryption at rest for user-provided secrets (e.g. a Moodle calendar URL, whose token is a bearer credential).

The key is derived from APP_SECRET_KEY with HKDF, so rotating APP_SECRET_KEY makes stored values unreadable
(callers treat that as "reconnect needed", never as a crash).
"""

from __future__ import annotations

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config.settings import get_settings


class SecretUnreadable(Exception):
    """Stored secret can't be decrypted (APP_SECRET_KEY changed)."""


@lru_cache
def _fernet(secret: str) -> Fernet:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"user-secrets-v1", info=b"fernet").derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet(get_settings().APP_SECRET_KEY.get_secret_value()).encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet(get_settings().APP_SECRET_KEY.get_secret_value()).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretUnreadable("stored secret can't be decrypted; reconnect it") from exc
