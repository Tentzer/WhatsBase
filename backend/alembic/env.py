"""Alembic environment — async, driven by app settings and ORM metadata.

The database URL comes from `app.core.config` (never hardcoded). Target
metadata is the ORM `Base` so future autogenerate sees every model. The initial
migration is authored by hand because autogenerate misses pgvector/halfvec,
HNSW/GIN index specifics, and RLS.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import context

from app.core.config import get_settings
from app.core.db import Base

# Import models so they register on Base.metadata.
from app.core import schema  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def _connect_args(url: str) -> dict:
    if "supabase.co" in url:
        return {"ssl": True}
    return {}


async def run_migrations_online() -> None:
    db_url = get_settings().database_url
    connectable = create_async_engine(
        db_url,
        poolclass=NullPool,
        connect_args=_connect_args(db_url),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
