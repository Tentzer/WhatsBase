"""arq task functions: process_incoming_message and send_outgoing.

M2 behaviour: process_incoming_message echoes any text message back.
The conversation agent replaces the echo in M4 — the queue contract
(payload shape, idempotency, outgoing via send_outgoing) stays the same.

Outgoing messages always go through the queue (send_outgoing task), never
directly from the adapter inside a task — SPEC invariant.
"""

from __future__ import annotations

import logging

from arq.connections import ArqRedis
from sqlalchemy import select

from app.adapters.whatsapp import get_adapter
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.schema import WhatsAppInstance

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL = 86_400  # 24 hours — long enough to cover any retry window


def _parse_allowlist(raw: str) -> set[str]:
    return {n.strip() for n in raw.split(",") if n.strip()}


def _is_allowed(chat_id: str, allowlist: set[str]) -> bool:
    """Return True if the chat may be replied to.

    Empty allowlist = no filter. Non-empty allowlist drops all groups (@g.us)
    and any direct chat whose bare digits aren't in the list.
    """
    if not allowlist:
        return True
    if chat_id.endswith("@g.us"):
        return False
    digits = chat_id.split("@", 1)[0]
    return digits in allowlist


async def process_incoming_message(ctx: dict, payload: dict) -> None:
    """Consume one normalised IncomingMessage dict from the queue.

    Steps:
      1. Idempotency: skip if this message_id was already processed (Redis NX).
      2. Log "incoming".
      3. Enqueue send_outgoing with the echo reply.
      4. Log "enqueue".
    """
    redis: ArqRedis = ctx["redis"]

    idempotency_key = f"msg:{payload['instance_id']}:{payload['message_id']}"
    was_set = await redis.set(idempotency_key, "1", nx=True, ex=_IDEMPOTENCY_TTL)
    if not was_set:
        logger.info("Duplicate message_id=%s — skipped", payload["message_id"])
        return

    logger.info(
        "incoming  chat=%s type=%s text=%r",
        payload["chat_id"],
        payload["type"],
        payload.get("text") or "[non-text]",
    )

    allowlist = _parse_allowlist(get_settings().allowed_test_numbers)
    if not _is_allowed(payload["chat_id"], allowlist):
        logger.info("dropped: sender %s not in allowlist", payload["chat_id"])
        return

    # M2: echo the text back. M4 replaces this with the conversation agent.
    reply_text: str
    if payload["type"] == "text" and payload.get("text"):
        reply_text = payload["text"]
    else:
        reply_text = "✓"  # ack non-text messages until the agent handles them

    outgoing = {
        "green_api_instance_id": payload["instance_id"],
        "chat_id": payload["chat_id"],
        "type": "text",
        "text": reply_text,
    }
    await redis.enqueue_job("send_outgoing", outgoing)
    logger.info("enqueue   send_outgoing chat=%s", payload["chat_id"])


async def send_outgoing(ctx: dict, payload: dict) -> None:
    """Send one outgoing message via the adapter.

    Loads the WhatsApp instance from the DB, creates the adapter, sends.
    Always queued — never called synchronously from within the agent loop.
    """
    green_api_id: str = payload["green_api_instance_id"]

    async with SessionLocal() as session:
        result = await session.execute(
            select(WhatsAppInstance).where(
                WhatsAppInstance.green_api_instance_id == green_api_id
            )
        )
        instance = result.scalar_one_or_none()

    if instance is None:
        logger.error("send_outgoing: no instance row for green_api_id=%s", green_api_id)
        return

    adapter = get_adapter(instance)

    if payload.get("type") == "image" and payload.get("image_url"):
        await adapter.send_image(
            payload["chat_id"],
            payload["image_url"],
            payload.get("caption", ""),
        )
    else:
        await adapter.send_text(payload["chat_id"], payload["text"])

    logger.info(
        "sent      chat=%s text=%r",
        payload["chat_id"],
        payload.get("text") or "[image]",
    )
