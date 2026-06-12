"""FastAPI application entrypoint.

Run locally: `uvicorn app.main:app --reload` (from the backend/ directory).
M1 mounts only the health router; feature routers land in later milestones.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.analytics import router as analytics_router
from app.api.health import router as health_router
from app.api.onboarding import router as onboarding_router
from app.core.config import get_settings
from app.intake.webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="WhatsApp AI Agent Builder Platform", version="0.1.0")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.app_base_url,
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    origin = request.headers.get("origin", "-")
    has_auth = "authorization" in request.headers
    has_uid = "x-supabase-user-id" in request.headers
    logger.info(
        "req: %s %s origin=%s has_auth=%s has_uid=%s",
        request.method,
        request.url.path,
        origin,
        has_auth,
        has_uid,
    )
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "res: %s %s status=%d %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


app.include_router(health_router)
app.include_router(onboarding_router)
app.include_router(analytics_router)
app.include_router(webhook_router)
