"""Langfuse v4 wiring — noop-safe when keys are absent.

Every LLM call, builder run, and conversation turn is decorated with @observe
and tagged with tenant_id. When Langfuse keys are not configured, observe
degrades to a transparent passthrough — but logs a WARNING exactly once so
silent degradation is immediately visible (unlike the previous silent noop).

v4 API changes from v2/v3:
  - observe: langfuse.observe  (was langfuse.decorators.observe)
  - update_trace: client.update_current_span(metadata=...)  (was langfuse_context.update_current_trace)
  - Langfuse() constructor registers the global singleton used by @observe
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from app.core.config import get_settings

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _langfuse_enabled() -> bool:
    s = get_settings()
    return bool(s.langfuse_public_key and s.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_langfuse() -> Any | None:
    """Return a configured Langfuse v4 client, or None when keys are absent.

    Also registers the client as the global singleton consumed by @observe.
    The lru_cache means the WARNING fires exactly once per process.
    """
    if not _langfuse_enabled():
        logger.warning(
            "Langfuse disabled: LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set — "
            "no traces will be emitted. Set both keys in .env to enable."
        )
        return None
    try:
        from langfuse import Langfuse

        s = get_settings()
        return Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
    except Exception as exc:
        logger.warning(
            "Langfuse disabled: initialization failed (%s) — no traces will be emitted.", exc
        )
        return None


def observe(*dargs: Any, **dkwargs: Any) -> Callable[[F], F]:
    """Drop-in for langfuse's @observe (v4), noop when Langfuse is disabled."""

    def decorator(func: F) -> F:
        client = get_langfuse()
        if client is None:
            return func
        try:
            from langfuse import observe as _observe

            return _observe(*dargs, **dkwargs)(func)
        except Exception as exc:
            logger.warning(
                "Langfuse @observe failed (%s) — falling back to noop for %s", exc, func.__name__
            )
            return func

    return decorator


def update_trace(**kwargs: Any) -> None:
    """Tag the current trace (e.g. tenant_id). Noop if Langfuse is disabled."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.update_current_span(metadata=kwargs)
    except Exception as exc:
        logger.debug("update_current_span failed (non-fatal): %s", exc)
    if "tenant_id" in kwargs:
        try:
            client.score_current_trace(
                name="tenant_id",
                value=str(kwargs["tenant_id"]),
                data_type="CATEGORICAL",
            )
        except Exception as exc:
            logger.debug("score_current_trace(tenant_id) failed (non-fatal): %s", exc)


def get_current_trace_id() -> str | None:
    """Return the active Langfuse trace id, or None when disabled/unavailable."""
    client = get_langfuse()
    if client is None:
        return None
    try:
        return client.get_current_trace_id()
    except Exception:  # noqa: BLE001 — tracing must never break a turn
        return None
