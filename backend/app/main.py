"""FastAPI application entrypoint.

Run locally: `uvicorn app.main:app --reload` (from the backend/ directory).
M1 mounts only the health router; feature routers land in later milestones.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_runtime import router as agent_runtime_router
from app.api.analytics import router as analytics_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.api.onboarding import router as onboarding_router
from app.core.config import get_settings
from app.intake.webhook import router as webhook_router

app = FastAPI(title="WhatsApp AI Agent Builder Platform", version="0.1.0")

settings = get_settings()
configured_origins = [
    origin.strip()
    for origin in settings.cors_allow_origins.split(",")
    if origin.strip()
]
default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://whatsbase.vercel.app",
]
allow_origins = sorted(set(default_origins + configured_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    # Also support preview deployments without explicit env edits.
    allow_origin_regex=r"https://.*\.vercel\.app",
)

app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(onboarding_router)
app.include_router(leads_router)
app.include_router(agent_runtime_router)
app.include_router(analytics_router)
