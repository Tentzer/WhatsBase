"""Health endpoint — liveness + a real DB ping."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Liveness probe — no DB dependency (used by Railway healthcheck)."""
    return {"status": "ok"}


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    settings = get_settings()
    db_status = "ok"
    db_error = ""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - report any DB failure as degraded
        db_status = "error"
        db_error = type(exc).__name__

    host_hint = "missing"
    if settings.database_url and "@" in settings.database_url:
        host_hint = settings.database_url.split("@", 1)[1].split("/", 1)[0]

    return {
        "status": "ok",
        "db": db_status,
        "db_error": db_error,
        "db_url_configured": str(bool(settings.database_url)),
        "db_host": host_hint,
    }
