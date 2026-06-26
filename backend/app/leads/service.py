from __future__ import annotations

import asyncio
import json
import logging
from contextlib import nullcontext
from datetime import datetime
from typing import Iterable, Literal, Sequence

from pydantic import BaseModel, Field
from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import LeadAutomationEventResponse, LeadResponse, LeadStatus
from app.core.models import get_model
from app.core.observability import get_langfuse, observe
from app.core.schema import Lead, LeadAutomationEvent, LeadProduct, Message, Product

logger = logging.getLogger(__name__)
_SUMMARY_WINDOW = 20
_JUDGE_WINDOW = 20


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


class LeadReengagementJudgeResult(BaseModel):
    decision: Literal["message_again", "do_not_message", "uncertain"] = "do_not_message"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_code: Literal[
        "hard_opt_out",
        "temporary_constraint",
        "price_timing",
        "no_response",
        "ambiguous",
        "other",
    ] = "ambiguous"
    recommended_message: str = ""


def _extract_json_block(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```json" in text:
        candidate = text.split("```json", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    try:
        return json.loads(text[first : last + 1])
    except json.JSONDecodeError:
        return None


def _contains_hard_opt_out(*texts: str) -> bool:
    merged = " ".join((text or "").lower() for text in texts)
    hard_markers = (
        "do not contact",
        "don't contact",
        "stop messaging",
        "stop contacting",
        "remove me",
        "unsubscribe",
        "never contact",
        "never message",
        "אל תפנה",
        "אל תפנו",
        "אל תשלח",
        "אל תשלחו",
        "תפסיקו",
        "להסיר אותי",
    )
    return any(marker in merged for marker in hard_markers)


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
    lf = get_langfuse()
    obs_ctx = (
        lf.start_as_current_observation(
            name="leads.summarize-llm",
            as_type="generation",
            model=model_cfg.name,
            model_parameters={"temperature": 0.1, "max_tokens": 500},
        )
        if lf is not None
        else nullcontext()
    )

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
        with obs_ctx:
            resp = await asyncio.to_thread(_call)
            if lf is not None:
                try:
                    lf.update_current_generation(
                        usage_details={
                            "input": resp.usage.input_tokens,
                            "output": resp.usage.output_tokens,
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
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


@observe(name="leads.reengagement_judge")
async def judge_reengagement_candidate(
    *,
    lead_summary: str | None,
    messages: Sequence[Message],
    status: LeadStatus,
    attempts: int,
    days_since_last_contact: int,
) -> LeadReengagementJudgeResult:
    window = list(messages)[-_JUDGE_WINDOW:]
    transcript_lines: list[str] = []
    for msg in window:
        content = (msg.content or "").strip()
        if not content:
            continue
        role = "customer" if msg.direction == "inbound" else "agent"
        transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines[-_JUDGE_WINDOW:])
    summary = (lead_summary or "").strip()

    if _contains_hard_opt_out(summary, transcript):
        return LeadReengagementJudgeResult(
            decision="do_not_message",
            confidence=1.0,
            reason_code="hard_opt_out",
            recommended_message="",
        )

    system_prompt = (
        "You are a safety-first judge for CRM re-engagement on WhatsApp.\n"
        "Goal: decide whether this lead should be contacted again now.\n"
        "Hard rule: if there is any explicit request not to be contacted again,\n"
        "or legal/privacy opt-out intent, return do_not_message.\n"
        "If uncertain, return do_not_message.\n"
        "Return JSON only with keys: decision, confidence, reason_code, recommended_message.\n"
        "Allowed decision: message_again | do_not_message | uncertain.\n"
        "Allowed reason_code: hard_opt_out | temporary_constraint | price_timing | "
        "no_response | ambiguous | other.\n"
        "recommended_message must be short, polite, and non-pushy.\n"
        "Do not invent specific prices, inventory, discounts, or delivery commitments."
    )
    user_prompt = (
        f"lead_status: {status}\n"
        f"attempt_count: {attempts}\n"
        f"days_since_last_contact: {days_since_last_contact}\n\n"
        f"conversation_summary:\n{summary or 'none'}\n\n"
        f"recent_transcript:\n{transcript or 'none'}"
    )
    model_cfg = get_model("setup_assistant")
    lf = get_langfuse()
    obs_ctx = (
        lf.start_as_current_observation(
            name="leads.reengagement-judge-llm",
            as_type="generation",
            model=model_cfg.name,
            model_parameters={"temperature": 0.0, "max_tokens": 350},
        )
        if lf is not None
        else nullcontext()
    )

    def _call():
        client = _get_anthropic_client()
        return client.messages.create(
            model=model_cfg.name,
            max_tokens=350,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

    try:
        with obs_ctx:
            resp = await asyncio.to_thread(_call)
            if lf is not None:
                try:
                    lf.update_current_generation(
                        usage_details={
                            "input": resp.usage.input_tokens,
                            "output": resp.usage.output_tokens,
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
        payload = _extract_json_block(_extract_text(resp))
        if payload:
            return LeadReengagementJudgeResult.model_validate(payload)
    except Exception:  # noqa: BLE001
        logger.exception("judge_reengagement_candidate failed")
    return LeadReengagementJudgeResult(
        decision="do_not_message",
        confidence=0.0,
        reason_code="ambiguous",
        recommended_message="",
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
        last_reengagement_at=lead.last_reengagement_at,
        last_reengagement_decision=lead.last_reengagement_decision,
        reengagement_attempt_count=lead.reengagement_attempt_count,
        reengagement_cooldown_until=lead.reengagement_cooldown_until,
        product_ids=[lp.product_id for lp in lead.interested_products],
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def lead_automation_event_to_response(
    event: LeadAutomationEvent,
) -> LeadAutomationEventResponse:
    return LeadAutomationEventResponse(
        id=event.id,
        lead_id=event.lead_id,
        automation_type=event.automation_type,
        decision=event.decision,
        reason=event.reason,
        scheduled_for=event.scheduled_for,
        sent_at=event.sent_at,
        idempotency_key=event.idempotency_key,
        payload_json=event.payload_json or {},
        created_at=event.created_at,
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

