"""The single SQLAlchemy engine/session factory, with user scoping enforced at the session level.

Every ORM model that carries `user_id` inherits `UserOwned`. A session opened with
`scoped_session_for(user_id)` automatically:
  * adds `WHERE <table>.user_id = :uid` to every ORM SELECT touching a UserOwned entity
    (including relationship loads) via `with_loader_criteria`;
  * stamps `user_id` on new objects and refuses to flush objects owned by another user.
A session without a user (`system_session()`) is only used by the scheduler, migrations and auth
lookups, and must be requested explicitly.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from app.config.settings import get_settings
from app.db.base import UserOwned


class ScopeViolation(PermissionError):
    pass


def _on_connect(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=10000")
    cur.close()


def make_engine(url: str) -> Engine:
    eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    event.listen(eng, "connect", _on_connect)
    return eng


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def set_engine(engine: Engine) -> None:
    """Used by tests to point the app at a temporary database."""
    global _engine, _factory
    _engine = engine
    _factory = sessionmaker(bind=engine, expire_on_commit=False)


def _factory_() -> sessionmaker[Session]:
    get_engine()
    assert _factory is not None
    return _factory


def scoped_session_for(user_id: str) -> Session:
    if not user_id:
        raise ScopeViolation("A user-scoped session requires a user_id")
    s = _factory_()()
    s.info["user_id"] = user_id
    return s


def system_session() -> Session:
    s = _factory_()()
    s.info["system"] = True
    return s


@contextmanager
def user_session(user_id: str) -> Iterator[Session]:
    s = scoped_session_for(user_id)
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


@contextmanager
def system_session_ctx() -> Iterator[Session]:
    s = system_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


@event.listens_for(Session, "do_orm_execute")
def _scope_selects(state: ORMExecuteState) -> None:
    uid = state.session.info.get("user_id")
    if uid is None:
        if not state.session.info.get("system"):
            raise ScopeViolation("ORM query on an unscoped session. Use scoped_session_for() or system_session().")
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(UserOwned, lambda cls: cls.user_id == uid, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _scope_writes(session: Session, _ctx: object, _instances: object) -> None:
    uid = session.info.get("user_id")
    if uid is None:
        return
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, UserOwned):
            if obj.user_id is None and obj in session.new:
                obj.user_id = uid
            elif obj.user_id != uid:
                raise ScopeViolation(f"{type(obj).__name__} belongs to another user")
