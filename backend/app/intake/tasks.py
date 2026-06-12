"""arq task functions: process_incoming_message and send_outgoing.

M2 behaviour: process_incoming_message echoes any text message back.
The conversation agent replaces the echo in M4 — the queue contract
(payload shape, idempotency, outgoing via send_outgoing) stays the same.

Outgoing messages always go through the queue (send_outgoing task), never
directly from the adapter inside a task — SPEC invariant.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from arq.connections import ArqRedis
from sqlalchemy import select

from app.adapters.whatsapp import get_adapter
from app.builder.agent import run_build as run_builder
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.schema import Agent, BuildRun, Product, WhatsAppInstance

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


def _resolve_demo_assets_dir() -> Path:
    """Locate demo_assets for CLI/demo builds (repo root or Docker image)."""
    base = Path(__file__).resolve()
    candidates = [
        base.parents[3] / "demo_assets",
        base.parents[2] / "demo_assets",
        Path("/app/demo_assets"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


async def _fail_build(
    tenant_id: str,
    build_run_id: str | None,
    reason: str,
) -> None:
    async with SessionLocal() as session:
        if build_run_id:
            result = await session.execute(
                select(BuildRun).where(
                    BuildRun.id == build_run_id,
                    BuildRun.tenant_id == tenant_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                report = dict(row.report or {})
                report["ui_progress_pct"] = 100
                report["ui_current_step"] = "finalize"
                row.status = "failed"
                row.error = reason
                row.report = report
                row.finished_at = datetime.now(timezone.utc)

        agent_result = await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
        agent = agent_result.scalar_one_or_none()
        if agent is not None:
            agent.status = "failed"
        await session.commit()
    logger.warning("run_build failed for tenant=%s: %s", tenant_id, reason)


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


async def run_build(ctx: dict, payload: dict) -> None:
    """Queue entrypoint for API-triggered builds.

    Expected payload:
      - tenant_id (required)
      - build_run_id (optional)
      - assets_dir (optional, defaults to repo demo_assets)
      - dry_run (optional, default False)
    """
    tenant_id = payload["tenant_id"]
    build_run_id = payload.get("build_run_id")
    dry_run = bool(payload.get("dry_run", False))
    assets_dir_raw = payload.get("assets_dir")
    settings = get_settings()

    catalog_source = "assets"
    async with SessionLocal() as session:
        if build_run_id:
            result = await session.execute(
                select(BuildRun).where(
                    BuildRun.id == build_run_id,
                    BuildRun.tenant_id == tenant_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                manifest = row.input_manifest or {}
                catalog_source = str(manifest.get("source") or manifest.get("catalog_source") or "assets")
                row.status = "running"
                report = dict(row.report or {})
                report["ui_progress_pct"] = 10
                report["ui_current_step"] = "collect_assets"
                row.report = report
                row.started_at = datetime.now(timezone.utc)
                await session.commit()

        if catalog_source == "api":
            product_count = await session.scalar(
                select(Product.id).where(Product.tenant_id == tenant_id).limit(1)
            )
            if product_count is None:
                await _fail_build(
                    tenant_id,
                    build_run_id,
                    "No products found for tenant — add products before building",
                )
                return
        else:
            assets_dir = Path(assets_dir_raw) if assets_dir_raw else _resolve_demo_assets_dir()
            if not assets_dir.exists():
                await _fail_build(
                    tenant_id,
                    build_run_id,
                    f"Assets directory not found: {assets_dir}",
                )
                return

    if not settings.anthropic_api_key or not settings.openai_api_key:
        await _fail_build(
            tenant_id,
            build_run_id,
            "Missing LLM credentials (ANTHROPIC_API_KEY and/or OPENAI_API_KEY)",
        )
        return

    assets_dir = Path(assets_dir_raw) if assets_dir_raw else _resolve_demo_assets_dir()

    try:
        report = await run_builder(
            tenant_id=tenant_id,
            assets_dir=assets_dir,
            dry_run=dry_run,
            build_run_id=build_run_id,
            catalog_source=catalog_source,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_build failed for tenant=%s", tenant_id)
        await _fail_build(tenant_id, build_run_id, str(exc))
        return

    if build_run_id and catalog_source == "assets":
        # API catalog builds finalize inside the pipeline; asset builds may need a sync pass.
        async with SessionLocal() as session:
            result = await session.execute(
                select(BuildRun).where(
                    BuildRun.id == build_run_id,
                    BuildRun.tenant_id == tenant_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None and row.status == "running":
                builder_report = report.to_dict()
                builder_report["ui_progress_pct"] = 100
                builder_report["ui_current_step"] = "finalize"
                row.report = builder_report
                row.status = "passed" if builder_report.get("self_test", {}).get("passed") else "failed"
                row.finished_at = datetime.now(timezone.utc)
                await session.commit()
