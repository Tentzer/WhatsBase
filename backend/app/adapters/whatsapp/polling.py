"""Async polling loop — one coroutine per active WhatsApp instance.

Polls receiveNotification → normalises → enqueues process_incoming_message
→ acks (deleteNotification). Feeds the same arq queue as the webhook path so
the rest of the system never knows which intake mode delivered the message.
"""

from __future__ import annotations

import asyncio
import logging

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.whatsapp import get_adapter
from app.core.schema import WhatsAppInstance

logger = logging.getLogger(__name__)

_EMPTY_QUEUE_SLEEP = 0.5   # seconds to sleep when no messages waiting
_ERROR_BACKOFF     = 5.0   # seconds to sleep after a transient API error


async def poll_instance(instance: WhatsAppInstance, redis: ArqRedis) -> None:
    """Continuously poll one instance and enqueue incoming messages.

    Never returns — runs until the process is killed or the coroutine is
    cancelled.
    """
    adapter = get_adapter(instance)
    instance_label = f"instance={instance.green_api_instance_id}"
    logger.info("Polling started for %s", instance_label)

    while True:
        try:
            messages = await adapter.get_incoming()

            if not messages:
                await asyncio.sleep(_EMPTY_QUEUE_SLEEP)
                continue

            for msg in messages:
                payload = {
                    "instance_id": msg.instance_id,
                    "message_id": msg.message_id,
                    "chat_id": msg.chat_id,
                    "sender": msg.sender,
                    "type": msg.type,
                    "text": msg.text,
                    "media_url": msg.media_url,
                    "caption": msg.caption,
                }
                await redis.enqueue_job("process_incoming_message", payload)
                logger.info(
                    "enqueued incoming message_id=%s chat=%s sender=%s",
                    msg.message_id,
                    msg.chat_id,
                    msg.sender,
                )

                if msg.notification_id is not None:
                    await adapter.ack(msg.notification_id)

        except asyncio.CancelledError:
            logger.info("Polling cancelled for %s", instance_label)
            raise
        except Exception:
            logger.exception("Poll error for %s — retrying in %.0fs", instance_label, _ERROR_BACKOFF)
            await asyncio.sleep(_ERROR_BACKOFF)
