"""Webhook intake for production (INTAKE_MODE=webhook).

Green API POSTs the notification body to /webhooks/greenapi/{instance_id}.
We validate, normalise, enqueue, and return 200 immediately — no blocking work.

For local development use the poller (INTAKE_MODE=polling). This route is
wired into the app now so it exists when M6 deploys to Railway.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.whatsapp.green_api import GreenApiAdapter
from app.core.db import get_session
from app.core.schema import WhatsAppInstance
from app.intake.queue import get_redis_pool

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/webhooks/greenapi/{instance_id}", status_code=200)
async def green_api_webhook(
    instance_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receive a Green API webhook notification, normalise, and enqueue."""
    body = await request.json()

    result = await session.execute(
        select(WhatsAppInstance).where(
            WhatsAppInstance.green_api_instance_id == instance_id
        )
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Adapter is used only for normalisation here; Green API webhook mode
    # doesn't need a live API call — body IS the notification.
    from app.core.crypto import decrypt_token
    from app.core.config import get_settings

    token = decrypt_token(instance.token_encrypted, get_settings().token_encryption_key)
    adapter = GreenApiAdapter(instance.green_api_instance_id, token)
    msg = adapter.normalize_webhook_payload(body)

    if msg is None:
        # Non-message webhook (delivery receipt, etc.) — ack and discard.
        return {"status": "ignored"}

    redis = await get_redis_pool()
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
    logger.info("webhook enqueued message_id=%s chat=%s", msg.message_id, msg.chat_id)
    return {"status": "queued"}
