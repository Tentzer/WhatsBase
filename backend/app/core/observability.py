"""Langfuse wiring — noop-safe when keys are absent.

Every LLM call, builder run, and conversation turn is decorated with `@observe`
and tagged with `tenant_id`. When Langfuse keys are not configured (tests, bare
local dev), `observe` degrades to a transparent passthrough so nothing breaks.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from app.core.config import get_settings

F = TypeVar("F", bound=Callable[..., Any])


def _langfuse_enabled() -> bool:
    s = get_settings()
    return bool(s.langfuse_public_key and s.langfuse_secret_key)


@lru_cache
def get_langfuse() -> Any | None:
    """Return a configured Langfuse client, or None when keys are absent."""
    if not _langfuse_enabled():
        return None
    from langfuse import Langfuse

    s = get_settings()
    return Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        host=s.langfuse_host,
    )


def observe(*dargs: Any, **dkwargs: Any) -> Callable[[F], F]:
    """Drop-in for langfuse's `@observe`, noop when Langfuse is disabled.

    Usage mirrors the real decorator::

        @observe()
        def run_build(...): ...

        @observe(name="conversation-turn")
        async def handle_turn(...): ...
    """

    def decorator(func: F) -> F:
        if not _langfuse_enabled():
            return func
        from langfuse.decorators import observe as _observe

        return _observe(*dargs, **dkwargs)(func)

    return decorator


def update_trace(**kwargs: Any) -> None:
    """Tag the current trace (e.g. tenant_id, conversation_id). Noop if disabled.

    langfuse 2.x `update_current_trace` has a fixed signature and rejects unknown
    kwargs like `tenant_id`, so domain tags are attached as trace metadata (and
    mirrored to `tags` for filtering in the Langfuse UI).
    """
    if not _langfuse_enabled():
        return
    from langfuse.decorators import langfuse_context

    tags = [f"{k}:{v}" for k, v in kwargs.items() if v is not None]
    langfuse_context.update_current_trace(metadata=kwargs, tags=tags)


def get_current_trace_id() -> str | None:
    """Return the active Langfuse trace id, or None when disabled/unavailable.

    Stored on the outbound message row (`messages.agent_trace_id`) as the
    debugging entry point for a conversation turn.
    """
    if not _langfuse_enabled():
        return None
    from langfuse.decorators import langfuse_context

    try:
        return langfuse_context.get_current_trace_id()
    except Exception:  # noqa: BLE001 — tracing must never break a turn
        return None
