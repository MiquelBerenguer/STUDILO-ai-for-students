from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser
from app.api.schemas import LoginIn, MeOut, RegisterIn
from app.auth.security import COOKIE_NAME, create_session, hash_password, revoke_session, verify_password
from app.config.settings import get_settings
from app.db.engine import system_session_ctx
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Constant-time-ish login: always run bcrypt even when the email does not exist.
_DUMMY_HASH = hash_password("studilo-dummy-password")


def _set_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=s.COOKIE_SECURE,
                    max_age=s.SESSION_TTL_DAYS * 86400, path="/")


@router.post("/register", response_model=MeOut, status_code=201)
def register(body: RegisterIn, response: Response) -> User:
    email = body.email.lower()
    with system_session_ctx() as db:
        if db.scalar(select(func.count()).select_from(User).where(User.email == email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        user = User(email=email, password_hash=hash_password(body.password),
                    display_name=body.display_name or email.split("@")[0])
        db.add(user)
        db.flush()
        _set_cookie(response, create_session(db, user.id))
        return user


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response) -> User:
    with system_session_ctx() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower()))
        if not verify_password(body.password, user.password_hash if user else _DUMMY_HASH) or user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
        _set_cookie(response, create_session(db, user.id))
        return user


@router.post("/logout", status_code=204)
def logout(response: Response, studilo_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> None:
    if studilo_session:
        with system_session_ctx() as db:
            revoke_session(db, studilo_session)
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser) -> User:
    with system_session_ctx() as sdb:
        row = sdb.get(User, user.id)
        assert row is not None
        return row
