"""Per-turn context assembly for the conversation agent.

Loads the tenant's live agent (system prompt) and the recent message history,
and resolves the conversation row. Current time/day is injected by the loop
(`guardrails.system_preamble`). All queries are tenant-scoped.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schema import Agent, Conversation, Message

HISTORY_WINDOW = 12


async def load_agent(session: AsyncSession, tenant_id: str) -> Agent | None:
    return (
        await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
    ).scalar_one_or_none()


async def get_or_create_conversation(
    session: AsyncSession, tenant_id: str, customer_phone: str
) -> Conversation:
    conversation = (
        await session.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.customer_phone == customer_phone,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant_id, customer_phone=customer_phone, status="open"
        )
        session.add(conversation)
        await session.flush()
    return conversation


async def recent_messages(
    session: AsyncSession, conversation_id: str, limit: int = HISTORY_WINDOW
) -> list[Message]:
    """The last `limit` messages for a conversation, oldest-first (the order the
    Messages API expects)."""
    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(reversed(rows))
