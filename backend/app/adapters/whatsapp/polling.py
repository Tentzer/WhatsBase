"""Async polling loop — one coroutine per active WhatsApp instance.

Polls receiveNotification → normalises → enqueues process_incoming_message
→ acks (deleteNotification). Periodically reconciles against the Green API
incoming journal so messages that never reached the notification queue are
still processed. Feeds the same arq queue as the webhook path.
"""

from __future__ import annotations

import asyncio
import logging
import time

from arq.connections import ArqRedis

from app.adapters.whatsapp import get_adapter
from app.adapters.whatsapp.base import IncomingMessage
from app.adapters.whatsapp.green_api import GreenApiAdapter
from app.core.schema import WhatsAppInstance

logger = logging.getLogger(__name__)

_EMPTY_QUEUE_SLEEP = 0.5   # seconds to sleep when no messages waiting
_ERROR_BACKOFF     = 5.0   # seconds to sleep after a transient API error
_JOURNAL_RECONCILE_SECONDS = 60
_JOURNAL_LOOKBACK_MINUTES = 5


async def _enqueue_incoming(
    redis: ArqRedis, msg: IncomingMessage, source: str
) -> None:
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
        "enqueued %s message_id=%s chat=%s sender=%s",
        source,
        msg.message_id,
        msg.chat_id,
        msg.sender,
    )


async def _reconcile_journal(
    adapter: GreenApiAdapter, redis: ArqRedis, instance_label: str
) -> None:
    """Enqueue any journal rows the real-time notification queue may have missed."""
    try:
        messages = await adapter.fetch_recent_journal_incoming(
            minutes=_JOURNAL_LOOKBACK_MINUTES
        )
    except Exception:
        logger.exception("journal reconcile failed for %s", instance_label)
        return
    if not messages:
        return
    logger.info(
        "journal reconcile: %d incoming row(s) in last %d min for %s",
        len(messages),
        _JOURNAL_LOOKBACK_MINUTES,
        instance_label,
    )
    for msg in messages:
        await _enqueue_incoming(redis, msg, "journal")


async def poll_instance(instance: WhatsAppInstance, redis: ArqRedis) -> None:
    """Continuously poll one instance and enqueue incoming messages.

    Never returns — runs until the process is killed or the coroutine is
    cancelled.
    """
    adapter = get_adapter(instance)
    instance_label = f"instance={instance.green_api_instance_id}"
    logger.info("Polling started for %s", instance_label)
    last_journal_reconcile = 0.0

    while True:
        try:
            now = time.monotonic()
            if (
                isinstance(adapter, GreenApiAdapter)
                and now - last_journal_reconcile >= _JOURNAL_RECONCILE_SECONDS
            ):
                last_journal_reconcile = now
                await _reconcile_journal(adapter, redis, instance_label)

            messages = await adapter.get_incoming()

            if not messages:
                # Sleep only when the Green API queue is empty. When we just acked
                # a delivery-status or other non-chat webhook, poll again immediately
                # so a large backlog (e.g. after group spam) does not block new DMs
                # for hours while sleeping 0.5s per junk notification.
                if not adapter.last_poll_had_notification:
                    await asyncio.sleep(_EMPTY_QUEUE_SLEEP)
                continue

            for msg in messages:
                await _enqueue_incoming(redis, msg, "notification")
                if msg.notification_id is not None:
                    await adapter.ack(msg.notification_id)

        except asyncio.CancelledError:
            logger.info("Polling cancelled for %s", instance_label)
            raise
        except Exception:
            logger.exception("Poll error for %s — retrying in %.0fs", instance_label, _ERROR_BACKOFF)
            await asyncio.sleep(_ERROR_BACKOFF)
