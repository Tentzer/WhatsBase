"""arq task functions: incoming-message debounce, the agent turn, and outgoing.

Flow (M4):
  process_incoming_message  — idempotency + allowlist, then buffer the message
                              into a per-(instance,chat) burst list and schedule
                              one debounced run_agent_turn 2.5s later.
  run_agent_turn            — drain the burst, resolve tenant, persist inbound,
                              run ONE conversation turn, persist + send replies.
  send_outgoing             — send a single message through the WhatsApp adapter.

Outgoing always goes through send_outgoing (queued), never directly from the
adapter inside the turn — SPEC invariant. The conversation runtime lives in
`app/runtime/` and is the only place the agent logic exists (shared with the
REST test-chat endpoint).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from arq.connections import ArqRedis
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.whatsapp import get_adapter
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.schema import (
    Agent,
    BuildRun,
    BusinessInfo,
    Lead,
    LeadAutomationEvent,
    LeadProduct,
    Message,
    Product,
    Conversation,
    Tenant,
    WhatsAppInstance,
)
from app.leads.service import (
    generate_lead_summary,
    judge_reengagement_candidate,
    normalize_phone,
    replace_lead_products,
    validate_tenant_products,
)
from app.runtime import memory
from app.runtime.context import TurnContext
from app.runtime.conversation import run_turn

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL = 86_400  # 24 hours — long enough to cover any retry window
_DEBOUNCE_SECONDS = 2.5  # wait this long, merging a burst from the same chat
_BURST_TTL = 60  # safety expiry on the burst buffer (seconds)
_SUMMARY_DEFER_SECONDS = 300  # summarize after 5m of chat inactivity
_SUMMARY_TOKEN_TTL = 3_600
_REENGAGEMENT_IDEMPOTENCY_TTL = 172_800


def _normalize_wa_digits(raw: str) -> str:
    """Normalize phone-ish ids for allowlist matching (972…, not 054…)."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("0") and len(digits) >= 9:
        return "972" + digits[1:]
    if len(digits) == 9 and digits.startswith("5"):
        return "972" + digits
    return digits


def _parse_allowlist(raw: str) -> set[str]:
    out: set[str] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        norm = _normalize_wa_digits(part)
        if norm:
            out.add(norm)
    return out


def _identity_keys(chat_id: str, sender: str | None) -> set[str]:
    """Keys to match against the allowlist for a direct (non-group) chat."""
    keys: set[str] = set()
    for part in (chat_id, sender or ""):
        if not part or part.endswith("@g.us"):
            continue
        prefix = part.split("@", 1)[0]
        norm = _normalize_wa_digits(prefix)
        if norm:
            keys.add(norm)
    return keys


def _is_allowed(chat_id: str, allowlist: set[str], sender: str | None = None) -> bool:
    """Return True if the chat may be replied to.

    Empty allowlist = no filter. Non-empty allowlist drops all groups (@g.us)
    and any direct chat whose phone isn't in the list. Uses both chat_id and
    sender so @lid chats (unsaved contacts) still match when sender is @c.us.
    """
    if not allowlist:
        return True
    if chat_id.endswith("@g.us"):
        return False
    keys = _identity_keys(chat_id, sender)
    return bool(keys & allowlist)


def _burst_key(instance_id: str, chat_id: str) -> str:
    return f"burst:{instance_id}:{chat_id}"


def _token_key(instance_id: str, chat_id: str) -> str:
    return f"debounce:{instance_id}:{chat_id}"


def _summary_token_key(instance_id: str, chat_id: str) -> str:
    return f"lead-summary:{instance_id}:{chat_id}"


def _reengagement_key(tenant_id: str, lead_id: str, day_key: str) -> str:
    return f"reengage:{tenant_id}:{lead_id}:{day_key}"


async def _upsert_lead_after_turn(
    *,
    session,
    tenant_id: str,
    customer_phone: str,
    conversation_id: str,
    result,
    now: datetime,
) -> None:
    phone = normalize_phone(customer_phone)
    lead = (
        await session.execute(
            select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone_number == phone)
        )
    ).scalar_one_or_none()

    if lead is None:
        tenant = await session.get(Tenant, tenant_id)
        lead = Lead(
            tenant_id=tenant_id,
            full_name=f"Lead {phone[-4:]}" if phone else "New Lead",
            phone_number=phone,
            status="pending",
            source="whatsapp_auto",
            business_name=tenant.name if tenant else None,
        )
        session.add(lead)
        await session.flush()

    lead.conversation_id = conversation_id
    lead.last_message_sent_at = now
    if not lead.business_name:
        tenant = await session.get(Tenant, tenant_id)
        lead.business_name = tenant.name if tenant else None

    product_ids = [card.id for card in result.cards if card.id]
    if product_ids:
        try:
            valid_product_ids = await validate_tenant_products(
                session, tenant_id=tenant_id, product_ids=product_ids
            )
            await replace_lead_products(
                session, lead_id=lead.id, product_ids=valid_product_ids
            )
        except ValueError:
            logger.warning(
                "lead product sync skipped tenant=%s phone=%s due to invalid product ids",
                tenant_id,
                phone,
            )

    # Summary runs in a separate idle job after 5m with no new inbound messages.


async def summarize_lead_after_idle(
    ctx: dict,
    instance_id: str,
    chat_id: str,
    tenant_id: str,
    customer_phone: str,
    token: int,
) -> None:
    """Summarize only after chat inactivity (latest token wins)."""
    redis: ArqRedis = ctx["redis"]
    current = await redis.get(_summary_token_key(instance_id, chat_id))
    if current is None or int(current) != token:
        return

    normalized_phone = normalize_phone(customer_phone)
    async with SessionLocal() as session:
        lead = (
            await session.execute(
                select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.phone_number == normalized_phone,
                )
            )
        ).scalar_one_or_none()
        if lead is None or not lead.conversation_id:
            return

        recent_messages = await memory.recent_messages(
            session, lead.conversation_id, limit=20
        )
        product_hints: list[str] = []
        lead_product_ids = [
            row[0]
            for row in (
                await session.execute(
                    select(LeadProduct.product_id).where(LeadProduct.lead_id == lead.id)
                )
            ).all()
        ]
        if lead_product_ids:
            products = (
                await session.execute(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.id.in_(lead_product_ids),
                    )
                )
            ).scalars().all()
            product_hints = [
                (product.name_en or product.name_he or product.stable_key)
                for product in products
            ]

        lead.last_conversation_summary = await generate_lead_summary(
            messages=recent_messages,
            stage=lead.status,  # type: ignore[arg-type]
            interested_product_hints=product_hints,
            previous_summary=lead.last_conversation_summary,
        )
        await session.commit()


async def process_incoming_message(ctx: dict, payload: dict) -> None:
    """Buffer one normalised IncomingMessage and (re)arm the debounce timer.

    Idempotency: each Green API message_id is processed exactly once.
    Debounce: a burst from the same (instance, chat) within 2.5s is merged into a
    single agent turn. A monotonic token ensures only the latest timer fires.
    """
    redis: ArqRedis = ctx["redis"]
    instance_id = payload["instance_id"]
    chat_id = payload["chat_id"]

    idempotency_key = f"msg:{instance_id}:{payload['message_id']}"
    was_set = await redis.set(idempotency_key, "1", nx=True, ex=_IDEMPOTENCY_TTL)
    if not was_set:
        logger.info("Duplicate message_id=%s — skipped", payload["message_id"])
        return

    allowlist = _parse_allowlist(get_settings().allowed_test_numbers)
    sender = payload.get("sender")
    if not _is_allowed(chat_id, allowlist, sender):
        logger.info(
            "dropped: chat=%s sender=%s not in allowlist (%d allowed numbers)",
            chat_id,
            sender,
            len(allowlist),
        )
        return

    logger.info(
        "incoming  chat=%s type=%s text=%r",
        chat_id,
        payload["type"],
        payload.get("text") or "[non-text]",
    )

    burst_key = _burst_key(instance_id, chat_id)
    await redis.rpush(burst_key, json.dumps(payload))
    await redis.expire(burst_key, _BURST_TTL)

    # Monotonic token: the latest message owns the timer; older timers no-op.
    token = await redis.incr(_token_key(instance_id, chat_id))
    await redis.expire(_token_key(instance_id, chat_id), _BURST_TTL)
    await redis.enqueue_job(
        "run_agent_turn",
        instance_id,
        chat_id,
        token,
        _defer_by=_DEBOUNCE_SECONDS,
    )


async def run_agent_turn(ctx: dict, instance_id: str, chat_id: str, token: int) -> None:
    """Debounced consumer: run one conversation turn for a merged message burst."""
    redis: ArqRedis = ctx["redis"]

    current = await redis.get(_token_key(instance_id, chat_id))
    if current is None or int(current) != token:
        return  # a newer message superseded this timer

    burst_key = _burst_key(instance_id, chat_id)
    raw_items = await redis.lrange(burst_key, 0, -1)
    await redis.delete(burst_key)
    if not raw_items:
        return

    burst = [json.loads(item) for item in raw_items]
    merged_text = "\n".join(
        (m.get("text") or m.get("caption") or "").strip()
        for m in burst
        if (m.get("text") or m.get("caption"))
    ).strip()
    user_text = merged_text or "(the customer sent a message with no text)"
    customer_phone = chat_id.split("@", 1)[0]
    normalized_phone = normalize_phone(customer_phone)

    async with SessionLocal() as session:
        instance = (
            await session.execute(
                select(WhatsAppInstance).where(
                    WhatsAppInstance.green_api_instance_id == instance_id
                )
            )
        ).scalar_one_or_none()
        if instance is None:
            logger.error("run_agent_turn: no instance row for %s", instance_id)
            return
        tenant_id = instance.tenant_id

        agent = await memory.load_agent(session, tenant_id)
        if agent is None or agent.status != "live" or not agent.system_prompt:
            logger.info(
                "run_agent_turn: agent not live for tenant=%s — skipping", tenant_id
            )
            return

        conversation = await memory.get_or_create_conversation(
            session, tenant_id, customer_phone
        )
        lead_for_context = (
            await session.execute(
                select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.phone_number == normalized_phone,
                )
            )
        ).scalar_one_or_none()
        history = await memory.recent_messages(session, conversation.id)

        now = datetime.now(timezone.utc)
        for msg in burst:
            session.add(
                Message(
                    conversation_id=conversation.id,
                    direction="inbound",
                    type="image" if msg.get("type") == "image" else "text",
                    content=msg.get("text") or msg.get("caption"),
                    media_url=msg.get("media_url"),
                )
            )
        await session.commit()

        async def _enqueue_outgoing(out_payload: dict) -> None:
            await redis.enqueue_job("send_outgoing", out_payload)

        turn_ctx = TurnContext(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            channel="whatsapp",
            green_api_instance_id=instance_id,
            chat_id=chat_id,
            enqueue_outgoing=_enqueue_outgoing,
        )
        result = await run_turn(
            tenant_id=tenant_id,
            system_prompt=agent.system_prompt,
            history=history,
            user_text=user_text,
            ctx=turn_ctx,
            lead_summary=(
                lead_for_context.last_conversation_summary
                if lead_for_context is not None
                else None
            ),
        )

        # Persist outbound: product cards (images, already enqueued by the tool)
        # plus the final text reply, all tagged with the Langfuse trace id.
        for card in result.cards:
            session.add(
                Message(
                    conversation_id=conversation.id,
                    direction="outbound",
                    type="image",
                    content=(card.name_he or card.name_en or None),
                    media_url=card.image_url,
                    agent_trace_id=result.trace_id,
                )
            )
        session.add(
            Message(
                conversation_id=conversation.id,
                direction="outbound",
                type="text",
                content=result.reply_text,
                agent_trace_id=result.trace_id,
            )
        )
        conversation.last_message_at = now
        await session.flush()
        await _upsert_lead_after_turn(
            session=session,
            tenant_id=tenant_id,
            customer_phone=customer_phone,
            conversation_id=conversation.id,
            result=result,
            now=now,
        )
        await session.commit()

        summary_token = await redis.incr(_summary_token_key(instance_id, chat_id))
        await redis.expire(_summary_token_key(instance_id, chat_id), _SUMMARY_TOKEN_TTL)
        await redis.enqueue_job(
            "summarize_lead_after_idle",
            instance_id,
            chat_id,
            tenant_id,
            customer_phone,
            summary_token,
            _defer_by=_SUMMARY_DEFER_SECONDS,
        )

    await redis.enqueue_job(
        "send_outgoing",
        {
            "green_api_instance_id": instance_id,
            "chat_id": chat_id,
            "type": "text",
            "text": result.reply_text,
        },
    )
    logger.info("turn done chat=%s cards=%d", chat_id, len(result.cards))


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


async def scan_reengagement_candidates(ctx: dict) -> None:
    """Daily scanner: enqueue tenant-scoped lead evaluation jobs."""
    settings = get_settings()
    if not settings.reengagement_enabled:
        return

    redis: ArqRedis = ctx["redis"]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, settings.reengagement_stale_days))
    day_key = now.date().isoformat()
    max_daily = max(1, settings.reengagement_max_daily_per_tenant)
    max_attempts = max(1, settings.reengagement_max_attempts_per_lead)

    async with SessionLocal() as session:
        last_activity_expr = func.coalesce(
            Lead.last_message_sent_at,
            Conversation.last_message_at,
            Lead.updated_at,
        )
        rows = (
            await session.execute(
                select(Lead.id, Lead.tenant_id)
                .outerjoin(Conversation, Conversation.id == Lead.conversation_id)
                .where(
                    Lead.status == "not_interested",
                    Lead.phone_number.is_not(None),
                    Lead.phone_number != "",
                    Lead.reengagement_attempt_count < max_attempts,
                    or_(
                        Lead.reengagement_cooldown_until.is_(None),
                        Lead.reengagement_cooldown_until <= now,
                    ),
                    last_activity_expr <= cutoff,
                )
                .order_by(Lead.tenant_id.asc(), last_activity_expr.asc())
            )
        ).all()

    per_tenant_counts: dict[str, int] = {}
    total = 0
    for lead_id, tenant_id in rows:
        count = per_tenant_counts.get(tenant_id, 0)
        if count >= max_daily:
            continue
        per_tenant_counts[tenant_id] = count + 1
        total += 1
        await redis.enqueue_job(
            "evaluate_reengagement_candidate",
            tenant_id,
            lead_id,
            day_key,
        )
    logger.info(
        "scan_reengagement_candidates queued=%d tenants=%d cutoff_days=%d",
        total,
        len(per_tenant_counts),
        settings.reengagement_stale_days,
    )


async def evaluate_reengagement_candidate(
    ctx: dict,
    tenant_id: str,
    lead_id: str,
    day_key: str | None = None,
) -> None:
    """Evaluate one stale lead and queue a safe follow-up when allowed."""
    settings = get_settings()
    if not settings.reengagement_enabled:
        return

    redis: ArqRedis = ctx["redis"]
    now = datetime.now(timezone.utc)
    schedule_day = day_key or now.date().isoformat()
    idempotency_key = _reengagement_key(tenant_id, lead_id, schedule_day)
    was_set = await redis.set(
        idempotency_key,
        "1",
        nx=True,
        ex=_REENGAGEMENT_IDEMPOTENCY_TTL,
    )
    if not was_set:
        return

    async with SessionLocal() as session:
        lead = (
            await session.execute(
                select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if lead is None:
            return
        if lead.status != "not_interested":
            return
        if lead.reengagement_attempt_count >= max(1, settings.reengagement_max_attempts_per_lead):
            return
        if (
            lead.reengagement_cooldown_until is not None
            and lead.reengagement_cooldown_until > now
        ):
            return

        active_agent = (
            await session.execute(
                select(Agent).where(Agent.tenant_id == tenant_id, Agent.status == "live")
            )
        ).scalar_one_or_none()
        if active_agent is None:
            return
        instance = (
            await session.execute(
                select(WhatsAppInstance)
                .where(WhatsAppInstance.tenant_id == tenant_id)
                .order_by(WhatsAppInstance.updated_at.desc())
            )
        ).scalars().first()
        if instance is None:
            return

        conversation = None
        if lead.conversation_id:
            conversation = await session.get(Conversation, lead.conversation_id)
        last_activity = lead.last_message_sent_at
        if conversation and conversation.last_message_at:
            if last_activity is None or conversation.last_message_at > last_activity:
                last_activity = conversation.last_message_at
        if last_activity is None:
            last_activity = lead.updated_at
        stale_days = max(1, settings.reengagement_stale_days)
        if last_activity > (now - timedelta(days=stale_days)):
            return

        recent_messages = (
            await memory.recent_messages(session, lead.conversation_id, limit=20)
            if lead.conversation_id
            else []
        )
        judge_result = await judge_reengagement_candidate(
            lead_summary=lead.last_conversation_summary,
            messages=recent_messages,
            status=lead.status,  # type: ignore[arg-type]
            attempts=lead.reengagement_attempt_count,
            days_since_last_contact=max(0, (now - last_activity).days),
        )

        effective_decision = judge_result.decision
        reason_code = judge_result.reason_code
        if judge_result.confidence < settings.reengagement_min_confidence:
            effective_decision = "do_not_message"
            reason_code = "ambiguous"
        if effective_decision == "uncertain":
            effective_decision = "do_not_message"

        event = LeadAutomationEvent(
            tenant_id=tenant_id,
            lead_id=lead.id,
            automation_type="reengagement",
            decision=effective_decision,
            reason=reason_code,
            scheduled_for=now,
            idempotency_key=idempotency_key,
            payload_json={
                "judge_decision": judge_result.decision,
                "judge_confidence": judge_result.confidence,
                "judge_reason_code": judge_result.reason_code,
                "message_preview": judge_result.recommended_message,
                "days_since_last_contact": max(0, (now - last_activity).days),
            },
        )
        session.add(event)
        lead.last_reengagement_decision = effective_decision

        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            return

        if effective_decision != "message_again" or settings.reengagement_dry_run:
            await session.commit()
            return

        normalized_phone = normalize_phone(lead.phone_number)
        if not normalized_phone:
            event.decision = "do_not_message"
            event.reason = "ambiguous"
            await session.commit()
            return
        chat_id = f"{normalized_phone}@c.us"
        allowlist = _parse_allowlist(settings.allowed_test_numbers)
        if allowlist and not _is_allowed(chat_id, allowlist):
            event.decision = "do_not_message"
            event.reason = "ambiguous"
            await session.commit()
            return

        message_text = judge_result.recommended_message.strip()
        if not message_text:
            message_text = (
                "Hi! Just checking in after our last chat. "
                "If timing works better now, I can help with options."
            )

        if conversation is None:
            conversation = await memory.get_or_create_conversation(
                session, tenant_id, normalized_phone
            )
            lead.conversation_id = conversation.id

        session.add(
            Message(
                conversation_id=conversation.id,
                direction="outbound",
                type="text",
                content=message_text,
            )
        )
        conversation.last_message_at = now
        lead.last_message_sent_at = now
        lead.last_reengagement_at = now
        lead.reengagement_attempt_count += 1
        lead.reengagement_cooldown_until = now + timedelta(
            days=max(1, settings.reengagement_cooldown_days)
        )
        event.sent_at = now
        event.payload_json = {
            **(event.payload_json or {}),
            "queued_chat_id": chat_id,
            "queued_message": message_text,
            "instance_id": instance.green_api_instance_id,
        }
        await session.commit()

    await redis.enqueue_job(
        "send_outgoing",
        {
            "green_api_instance_id": instance.green_api_instance_id,
            "chat_id": chat_id,
            "type": "text",
            "text": message_text,
        },
    )
    logger.info(
        "reengagement queued tenant=%s lead=%s",
        tenant_id,
        lead_id,
    )


async def _update_build_run(
    session,
    build_run_id: str | None,
    tenant_id: str,
    *,
    status: str,
    progress: int,
    step: str,
    extra_report: dict | None = None,
    error: str | None = None,
) -> None:
    if not build_run_id:
        return
    row = (
        await session.execute(
            select(BuildRun).where(
                BuildRun.id == build_run_id, BuildRun.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return
    row.status = status
    report = dict(row.report or {})
    report["ui_progress_pct"] = progress
    report["ui_current_step"] = step
    if extra_report:
        report.update(extra_report)
    row.report = report
    if error is not None:
        row.error = error
    if status == "running" and not row.started_at:
        row.started_at = datetime.now(timezone.utc)
    if status in {"passed", "failed"}:
        row.finished_at = datetime.now(timezone.utc)
    await session.commit()


async def _fail_build(tenant_id: str, build_run_id: str | None, error: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Agent).where(Agent.tenant_id == tenant_id).values(status="failed")
        )
        await session.commit()
        await _update_build_run(
            session, build_run_id, tenant_id,
            status="failed", progress=100, step="finalize", error=error,
        )


async def run_build(ctx: dict, payload: dict) -> None:
    """API/wizard build: stage onboarding data, then run the full Builder agent."""
    import shutil

    from app.builder.agent import run_build as run_builder_agent
    from app.builder.onboarding_assets import materialize_tenant_assets

    tenant_id = payload["tenant_id"]
    build_run_id = payload.get("build_run_id")
    settings = get_settings()

    if not settings.openai_api_key or not settings.anthropic_api_key:
        logger.error("run_build: missing LLM credentials for tenant=%s", tenant_id)
        await _fail_build(tenant_id, build_run_id, "Missing LLM credentials")
        return

    assets_dir: Path | None = None
    try:
        async with SessionLocal() as session:
            await _update_build_run(
                session,
                build_run_id,
                tenant_id,
                status="running",
                progress=10,
                step="collect_assets",
            )
            assets_dir = await materialize_tenant_assets(session, tenant_id)

        await run_builder_agent(
            tenant_id,
            assets_dir,
            dry_run=False,
            build_run_id=build_run_id,
        )
        logger.info("run_build: full builder agent finished for tenant=%s", tenant_id)
    except ValueError as exc:
        logger.warning("run_build: invalid catalog for tenant=%s: %s", tenant_id, exc)
        await _fail_build(tenant_id, build_run_id, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_build failed for tenant=%s", tenant_id)
        await _fail_build(tenant_id, build_run_id, str(exc))
    finally:
        if assets_dir is not None:
            shutil.rmtree(assets_dir, ignore_errors=True)


async def run_incremental_build(ctx: dict, payload: dict) -> None:
    """Embed only newly added products — no system-prompt regeneration.

    Used after the owner adds catalog items while the agent is already live.
    Existing embeddings and the system prompt are left unchanged.
    """
    import json
    from pathlib import Path

    from app.builder.context import BuildContext
    from app.builder.tools.knowledge import index_new_product_embeddings

    tenant_id = payload["tenant_id"]
    build_run_id = payload.get("build_run_id")
    settings = get_settings()

    if not settings.openai_api_key:
        logger.error("run_incremental_build: missing OPENAI_API_KEY for tenant=%s", tenant_id)
        async with SessionLocal() as session:
            await _update_build_run(
                session,
                build_run_id,
                tenant_id,
                status="failed",
                progress=100,
                step="index_embeddings",
                error="Missing OPENAI_API_KEY",
            )
        return

    try:
        async with SessionLocal() as session:
            agent = (
                await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
            ).scalar_one_or_none()
            if agent is None or agent.status != "live" or not agent.system_prompt:
                await _update_build_run(
                    session,
                    build_run_id,
                    tenant_id,
                    status="failed",
                    progress=100,
                    step="index_embeddings",
                    error="Agent must be live before incremental indexing",
                )
                return

            await _update_build_run(
                session,
                build_run_id,
                tenant_id,
                status="running",
                progress=30,
                step="index_embeddings",
            )

            build_ctx = BuildContext(
                tenant_id=tenant_id,
                assets_dir=Path("."),
                dry_run=False,
                session=session,
            )
            result = json.loads(await index_new_product_embeddings(build_ctx))
            new_count = int(result.get("new_products", 0))

            await _update_build_run(
                session,
                build_run_id,
                tenant_id,
                status="passed",
                progress=100,
                step="finalize",
                extra_report={
                    "mode": "incremental",
                    "new_products_indexed": new_count,
                    "products_detected": new_count,
                    "products_created": new_count,
                },
            )
        logger.info(
            "run_incremental_build: tenant=%s indexed %d new product(s)",
            tenant_id,
            new_count,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_incremental_build failed for tenant=%s", tenant_id)
        async with SessionLocal() as session:
            await _update_build_run(
                session,
                build_run_id,
                tenant_id,
                status="failed",
                progress=100,
                step="index_embeddings",
                error=str(exc),
            )
