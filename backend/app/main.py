"""FastAPI application entrypoint.

Run locally: `uvicorn app.main:app --reload` (from the backend/ directory).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.agent_runtime import router as agent_runtime_router
from app.api.analytics import router as analytics_router
from app.api.health import router as health_router
from app.api.onboarding import router as onboarding_router
from app.intake.webhook import router as webhook_router

app = FastAPI(title="WhatsApp AI Agent Builder Platform", version="0.1.0")
app.include_router(health_router)
app.include_router(analytics_router)
app.include_router(onboarding_router)
app.include_router(agent_runtime_router)
app.include_router(webhook_router)
