from __future__ import annotations

from alembic import context

from app.config.settings import get_settings
from app.db import models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.db.engine import make_engine

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """sqlite-vec virtual tables (and their shadow tables) are managed by hand, never by autogenerate."""
    return not (type_ == "table" and name and name.startswith("vec_"))


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is not None:
        context.configure(connection=connectable, target_metadata=target_metadata, render_as_batch=True,
                          include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = make_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                          include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
