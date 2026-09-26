"""Request dependencies. `CurrentUser` is required by every non-public route.

`get_db` yields a session scoped to the authenticated user (see app.db.engine): every ORM query
made through it is filtered by user_id at the data-access layer, not in the handlers.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import COOKIE_NAME, resolve_session
from app.db.engine import scoped_session_for, system_session_ctx


@dataclass(frozen=True)
class AuthedUser:
    id: str
    email: str
    display_name: str
    journey_state: str
    timezone: str


def current_user(session_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> AuthedUser:
    if not session_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    with system_session_ctx() as db:
        user = resolve_session(db, session_token)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        return AuthedUser(user.id, user.email, user.display_name, user.journey_state, user.timezone)


CurrentUser = Annotated[AuthedUser, Depends(current_user)]


def get_db(user: CurrentUser) -> Iterator[Session]:
    s = scoped_session_for(user.id)
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


DB = Annotated[Session, Depends(get_db)]


T = TypeVar("T")


def get_or_404(db: Session, model: type[T], obj_id: str) -> T:
    """Scoped get: another user's id is indistinguishable from a missing id."""
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj
