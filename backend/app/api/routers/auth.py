from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser
from app.api.schemas import GuestIn, LoginIn, MeOut, RegisterIn
from app.auth.ratelimit import RateLimiter
from app.auth.security import COOKIE_NAME, create_session, hash_password, revoke_session, verify_password
from app.config.settings import get_settings
from app.db.engine import system_session_ctx, user_session
from app.db.models import User
from app.orchestrator import cards

router = APIRouter(prefix="/auth", tags=["auth"])

guest_limiter = RateLimiter(limit=20, window_s=3600)  # guest sessions per client IP per hour

# Constant-time-ish login: always run bcrypt even when the email does not exist.
_TIMING_HASH = hash_password("timing-equaliser")


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
        if not verify_password(body.password, user.password_hash if user else _TIMING_HASH) or user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
        _set_cookie(response, create_session(db, user.id))
        return user


@router.post("/guest", response_model=MeOut, status_code=201)
def guest(body: GuestIn, request: Request, response: Response) -> User:
    """Onboarding without a registration wall (UX.md §8): a real, scoped user without credentials yet."""
    if not guest_limiter.allow(request.client.host if request.client else "unknown"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many new sessions from this network. Try later.")
    with system_session_ctx() as db:
        user = User(email=None, password_hash=None, display_name="", timezone=body.timezone or "Europe/Madrid")
        db.add(user)
        db.flush()
        _set_cookie(response, create_session(db, user.id))
        user_id = user.id
    with user_session(user_id) as udb:
        cards.create_card(udb, "account_claim", "Save your account so your notes are safe",
                          body="Add an email and password whenever you like. Until then this browser is your key.",
                          actions=[cards.action("claim", "Save account", "credentials", primary=True)],
                          dedupe_key="account_claim")
    with system_session_ctx() as db:
        return db.get(User, user_id)  # type: ignore[return-value]


@router.post("/claim", response_model=MeOut)
def claim(body: RegisterIn, user: CurrentUser) -> User:
    """A guest sets email + password; all data stays (same user id)."""
    email = body.email.lower()
    with system_session_ctx() as db:
        row = db.get(User, user.id)
        assert row is not None
        if not row.is_guest:
            raise HTTPException(status.HTTP_409_CONFLICT, "This account already has an email")
        if db.scalar(select(func.count()).select_from(User).where(User.email == email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        row.email, row.password_hash = email, hash_password(body.password)
        row.display_name = body.display_name or row.display_name or email.split("@")[0]
        db.flush()
    with user_session(user.id) as udb:
        cards.resolve_matching(udb, ("account_claim",))
    with system_session_ctx() as db:
        return db.get(User, user.id)  # type: ignore[return-value]


@router.post("/logout", status_code=204)
def logout(response: Response, session_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> None:
    if session_token:
        with system_session_ctx() as db:
            revoke_session(db, session_token)
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser) -> User:
    with system_session_ctx() as sdb:
        row = sdb.get(User, user.id)
        assert row is not None
        return row
