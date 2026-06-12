from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.schema import User
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    supabase_user_id: str
    email: str
    user_row: User | None


async def get_auth_context(
    authorization: str | None = Header(default=None),
    x_supabase_user_id: str | None = Header(default=None),
    x_supabase_email: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    supabase_user_id: str | None = None
    email: str | None = None

    has_bearer = bool(authorization and authorization.lower().startswith("bearer "))
    has_fallback = bool(x_supabase_user_id)
    logger.info(
        "auth_context_attempt: has_bearer=%s has_fallback_headers=%s",
        has_bearer,
        has_fallback,
    )

    if has_bearer:
        token = authorization.split(" ", 1)[1].strip()  # type: ignore[union-attr]
        if token:
            supabase = get_supabase()
            try:
                auth_response = await asyncio.to_thread(supabase.auth.get_user, token)
                user_obj = getattr(auth_response, "user", None) if auth_response else None
                if user_obj is not None and getattr(user_obj, "id", None):
                    supabase_user_id = str(user_obj.id)
                    email = str(getattr(user_obj, "email", "") or "")
                    logger.info(
                        "auth_bearer_ok: supabase_user_id=%.8s...", supabase_user_id
                    )
                else:
                    logger.warning("auth_bearer_invalid: get_user returned no user object")
            except Exception as exc:  # noqa: BLE001
                logger.warning("auth_bearer_error: %s – falling back to headers", exc)

    # Fallback path: bearer verification failed or was absent but explicit
    # identity headers were sent (used in local-tunnel / development flows).
    if not supabase_user_id and x_supabase_user_id:
        supabase_user_id = x_supabase_user_id
        email = x_supabase_email or ""
        logger.info(
            "auth_fallback_headers: supabase_user_id=%.8s...", supabase_user_id
        )

    if not supabase_user_id:
        logger.warning(
            "auth_rejected: no bearer and no fallback headers present"
        )
        raise HTTPException(status_code=401, detail="Missing or invalid auth context")

    result = await session.execute(
        select(User).where(User.supabase_user_id == supabase_user_id)
    )
    user_row = result.scalar_one_or_none()

    logger.info(
        "auth_resolved: supabase_user_id=%.8s... user_row=%s tenant_id=%s",
        supabase_user_id,
        user_row.id if user_row else None,
        user_row.tenant_id if user_row else None,
    )

    return AuthContext(
        supabase_user_id=supabase_user_id,
        email=email,
        user_row=user_row,
    )


def require_tenant(ctx: AuthContext) -> str:
    if ctx.user_row is None or not ctx.user_row.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant is not initialized for this user")
    return ctx.user_row.tenant_id
