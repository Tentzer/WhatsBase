"""Polling-mode intake entrypoint — one asyncio task per active instance.

Run with:  python -m app.poller   (from backend/)

Loads all whatsapp_instances where intake_mode='polling', starts one
poll_instance coroutine per row, and runs until killed. Use this for local
development and as a Sunday-demo fallback (no public URL required).
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    stream=sys.stdout,
)

from sqlalchemy import select

from app.adapters.whatsapp.polling import poll_instance
from app.core.db import SessionLocal
from app.core.schema import WhatsAppInstance
from app.intake.queue import get_redis_pool

logger = logging.getLogger(__name__)


_POLLER_RETRY_SECONDS = 30


async def _load_polling_instances() -> list[WhatsAppInstance]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(WhatsAppInstance).where(WhatsAppInstance.intake_mode == "polling")
        )
        return list(result.scalars().all())


async def main() -> None:
    redis = await get_redis_pool()

    while True:
        instances = await _load_polling_instances()
        if not instances:
            logger.warning(
                "No polling-mode WhatsApp instances yet — retrying in %ds. "
                "Connect WhatsApp in the app (INTAKE_MODE=polling).",
                _POLLER_RETRY_SECONDS,
            )
            await asyncio.sleep(_POLLER_RETRY_SECONDS)
            continue

        logger.info("Found %d polling instance(s)", len(instances))
        tasks = [asyncio.create_task(poll_instance(inst, redis)) for inst in instances]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        break  # gather only returns if all poll tasks exit (should not happen normally)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Poller stopped.")
