"""handoff_to_human tool — escalate the conversation to the business owner."""

from __future__ import annotations

import logging

from sqlalchemy import update

from app.core.db import SessionLocal
from app.core.observability import observe
from app.core.schema import Conversation
from app.runtime.context import TurnContext

logger = logging.getLogger(__name__)


@observe(name="runtime.tool.handoff_to_human")
async def run(ctx: TurnContext, reason: str = "", **_ignored: object) -> str:
    ctx.handoff = True
    ctx.handoff_reason = reason

    if ctx.conversation_id:
        async with SessionLocal() as session:
            await session.execute(
                update(Conversation)
                .where(
                    Conversation.id == ctx.conversation_id,
                    Conversation.tenant_id == ctx.tenant_id,
                )
                .values(status="handoff")
            )
            await session.commit()

    # Stub owner notification — wired to a real channel (email/WhatsApp) later.
    logger.info(
        "handoff_to_human tenant=%s conversation=%s reason=%r",
        ctx.tenant_id,
        ctx.conversation_id,
        reason,
    )
    return (
        "Escalated to a human — a team member will follow up. "
        "Tell the customer politely that a person will get back to them."
    )
