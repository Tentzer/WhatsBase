"""Flush arq queue + result keys (leaves idempotency keys intact).

Drops anything queued from prior test runs so they don't get echoed when
the worker restarts.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as redis

from app.core.config import get_settings


async def main() -> None:
    r = redis.from_url(get_settings().redis_url)

    # arq default keys: arq:queue (sorted set), arq:result:* (job results),
    # arq:job:* (job data), arq:in-progress:* (running). Idempotency keys are
    # msg:* — preserve those.
    patterns = ["arq:*"]
    total = 0
    for pat in patterns:
        async for key in r.scan_iter(match=pat, count=500):
            await r.delete(key)
            total += 1

    print(f"Deleted {total} arq queue/job/result keys.")
    print("Idempotency keys (msg:*) left untouched.")
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
