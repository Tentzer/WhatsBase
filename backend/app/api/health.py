"""Health endpoint — liveness + a real DB ping."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Liveness probe with no DB dependency (safe for platform healthchecks)."""
    return {"status": "ok"}


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - report any DB failure as degraded
        db_status = "error"
    return {"status": "ok", "db": db_status}
