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
from datetime import datetime, timezone
from pathlib import Path

from arq.connections import ArqRedis
from sqlalchemy import select, update

from app.adapters.whatsapp import get_adapter
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.schema import Agent, BuildRun, BusinessInfo, Message, Product, WhatsAppInstance
from app.runtime import memory
from app.runtime.context import TurnContext
from app.runtime.conversation import run_turn

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL = 86_400  # 24 hours — long enough to cover any retry window
_DEBOUNCE_SECONDS = 2.5  # wait this long, merging a burst from the same chat
_BURST_TTL = 60  # safety expiry on the burst buffer (seconds)


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
        await session.commit()

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
