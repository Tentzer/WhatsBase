"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

Builder writes and runtime reads through this single async session layer.
No sync engine — the whole backend is async (asyncpg driver).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models (see schema.py)."""


_settings = get_settings()


def _connect_args(database_url: str) -> dict:
    """Supabase Postgres requires SSL from external hosts (e.g. Railway)."""
    if "supabase.co" in database_url:
        # "require" avoids CERTIFICATE_VERIFY_FAILED with Supabase's cert chain.
        return {"ssl": "require"}
    return {}


_db_url = _settings.database_url or "postgresql+asyncpg://localhost/postgres"

# `future=True` is default in SQLAlchemy 2. pool_pre_ping guards against
# Supabase pooler dropping idle connections.
engine = create_async_engine(
    _db_url,
    connect_args=_connect_args(_db_url),
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with SessionLocal() as session:
        yield session
