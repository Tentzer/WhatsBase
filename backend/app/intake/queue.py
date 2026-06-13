"""arq worker settings and Redis pool factory.

WorkerSettings is the single descriptor arq (and `python -m app.worker`) reads.
get_redis_pool() gives callers (the poller, the webhook handler) an enqueue-
capable pool without duplicating the connection config.
"""

from __future__ import annotations

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def get_redis_pool() -> ArqRedis:
    """Return an arq Redis pool that can enqueue jobs."""
    return await create_pool(_redis_settings())


# Imported by app/worker.py — arq reads this class to start the worker.
class WorkerSettings:
    from app.intake import tasks as _tasks  # evaluated at import time

    functions = [
        _tasks.process_incoming_message,
        _tasks.run_agent_turn,
        _tasks.send_outgoing,
        _tasks.run_build,
        _tasks.run_incremental_build,
    ]
    redis_settings = _redis_settings()

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        ctx["redis_pool"] = await get_redis_pool()

    @staticmethod
    async def on_shutdown(ctx: dict) -> None:
        pool: ArqRedis = ctx.get("redis_pool")
        if pool:
            await pool.aclose()
