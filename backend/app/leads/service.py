from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import LeadResponse, LeadStatus
from app.core.models import get_model
from app.core.observability import observe
from app.core.schema import Lead, LeadProduct, Message, Product

logger = logging.getLogger(__name__)
_SUMMARY_WINDOW = 20


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return raw.strip()
    if digits.startswith("0") and len(digits) >= 9:
        return f"972{digits[1:]}"
    return digits


def _extract_text(resp) -> str:
    chunks: list[str] = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            chunks.append(block.text)
    return "\n".join(chunks).strip()


def _fallback_summary(
    *,
    user_text: str,
    product_hints: Sequence[str],
    stage: LeadStatus,
) -> str:
    interest = ", ".join(product_hints) if product_hints else "No explicit product yet."
    return "\n".join(
        [
            f"customer intent: {user_text or 'General inquiry or ongoing chat.'}",
            f"interested products (from sent cards / mentioned products): {interest}",
            "objections (price, delivery, etc.): Not clearly identified yet.",
            f"current stage (pending/qualified/not_interested/success): {stage}",
            "next suggested follow-up: Ask a focused qualification question and propose a clear next step.",
        ]
    )


def _get_anthropic_client():
    from anthropic import Anthropic

    from app.core.config import get_settings

    return Anthropic(api_key=get_settings().anthropic_api_key)


@observe(name="leads.summarize")
async def generate_lead_summary(
    *,
    messages: Sequence[Message],
    stage: LeadStatus,
    interested_product_hints: Sequence[str],
    previous_summary: str | None = None,
) -> str:
    """Always run a lightweight summarization LLM call for lead context."""
    window = list(messages)[-_SUMMARY_WINDOW:]
    if not window:
        return _fallback_summary(user_text="", product_hints=interested_product_hints, stage=stage)

    transcript_lines: list[str] = []
    for msg in window:
        content = (msg.content or "").strip()
        if not content:
            continue
        role = "customer" if msg.direction == "inbound" else "agent"
        transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines[-_SUMMARY_WINDOW:])
    product_hint_text = ", ".join(interested_product_hints) if interested_product_hints else "none"

    system_prompt = (
        "You summarize a sales lead conversation for CRM.\n"
        "Merge previous_summary with the latest transcript into one updated memory.\n"
        "Return exactly 5 lines, no markdown bullets, no extra text.\n"
        "Each line must start with exactly one of these labels:\n"
        "customer intent:\n"
        "interested products (from sent cards / mentioned products):\n"
        "objections (price, delivery, etc.):\n"
        "current stage (pending/qualified/not_interested/success):\n"
        "next suggested follow-up:\n"
        "Use only facts from the transcript and product hints. If unknown, say 'Unknown'."
    )
    user_prompt = (
        f"stage: {stage}\n"
        f"product_hints: {product_hint_text}\n\n"
        f"previous_summary:\n{previous_summary or 'none'}\n\n"
        f"transcript:\n{transcript}"
    )
    model_cfg = get_model("setup_assistant")

    def _call():
        client = _get_anthropic_client()
        return client.messages.create(
            model=model_cfg.name,
            max_tokens=500,
            temperature=0.1,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

    try:
        resp = await asyncio.to_thread(_call)
        text = _extract_text(resp)
        if text:
            return text
    except Exception:  # noqa: BLE001
        logger.exception("generate_lead_summary failed")
    # We still return a structured fallback if the model call fails.
    last_customer_text = next(
        ((msg.content or "").strip() for msg in reversed(window) if msg.direction == "inbound"),
        "",
    )
    return _fallback_summary(
        user_text=last_customer_text,
        product_hints=interested_product_hints,
        stage=stage,
    )


def lead_to_response(lead: Lead) -> LeadResponse:
    return LeadResponse(
        id=lead.id,
        full_name=lead.full_name,
        phone_number=lead.phone_number,
        status=lead.status,  # type: ignore[arg-type]
        did_buy=lead.did_buy,
        business_name=lead.business_name,
        source=lead.source,
        notes=lead.notes,
        next_follow_up_at=lead.next_follow_up_at,
        last_message_sent_at=lead.last_message_sent_at,
        last_conversation_summary=lead.last_conversation_summary,
        product_ids=[lp.product_id for lp in lead.interested_products],
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def lead_query_for_tenant(tenant_id: str) -> Select[tuple[Lead]]:
    return (
        select(Lead)
        .where(Lead.tenant_id == tenant_id)
        .options(selectinload(Lead.interested_products))
    )


async def validate_tenant_products(
    session: AsyncSession,
    *,
    tenant_id: str,
    product_ids: Iterable[str],
) -> list[str]:
    deduped = list(dict.fromkeys(pid for pid in product_ids if pid))
    if not deduped:
        return []
    rows = (
        await session.execute(
            select(Product.id).where(Product.tenant_id == tenant_id, Product.id.in_(deduped))
        )
    ).all()
    found = {row[0] for row in rows}
    missing = [pid for pid in deduped if pid not in found]
    if missing:
        raise ValueError("Some products are missing or do not belong to this tenant")
    return deduped


async def replace_lead_products(
    session: AsyncSession,
    *,
    lead_id: str,
    product_ids: Sequence[str],
) -> None:
    await session.execute(delete(LeadProduct).where(LeadProduct.lead_id == lead_id))
    for product_id in product_ids:
        session.add(LeadProduct(lead_id=lead_id, product_id=product_id))

