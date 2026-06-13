"""Builder agent loop — plain Anthropic tool-calling while-loop (no frameworks)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from app.builder.context import BuildContext
from app.builder.prompts import BUILDER_SYSTEM

# Stable system prompt wrapped as a cached content block.
# Cache TTL is 5 minutes; repeated builder turns pay only the cached-token rate.
_CACHED_SYSTEM = [{"type": "text", "text": BUILDER_SYSTEM, "cache_control": {"type": "ephemeral"}}]
from app.builder.report import BuildReport
from app.builder.tools import TOOL_SCHEMAS, dispatch
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import get_model
from contextlib import nullcontext

from app.core.observability import get_langfuse, observe, update_trace
from app.core.schema import Agent, BuildRun, Tenant

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 40  # safety cap; a full build needs ~30 tool calls


@lru_cache(maxsize=1)
def _get_anthropic():
    from anthropic import Anthropic

    return Anthropic(api_key=get_settings().anthropic_api_key)


@observe(name="builder.run")
async def run_build(
    tenant_id: str,
    assets_dir: Path,
    dry_run: bool = False,
    *,
    build_run_id: str | None = None,
    catalog_source: str = "assets",
) -> BuildReport:
    """Run the full Builder agent for one tenant. Returns the BuildReport."""
    update_trace(tenant_id=tenant_id)

    async with SessionLocal() as session:
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found in database")

        if build_run_id:
            existing = await session.execute(
                select(BuildRun).where(
                    BuildRun.id == build_run_id,
                    BuildRun.tenant_id == tenant_id,
                )
            )
            if existing.scalar_one_or_none() is None:
                raise ValueError(f"Build run {build_run_id!r} not found for tenant {tenant_id!r}")
        else:
            build_run = BuildRun(
                tenant_id=tenant_id,
                status="running",
                input_manifest={
                    "assets_dir": str(assets_dir),
                    "dry_run": dry_run,
                    "catalog_source": catalog_source,
                    "images": sorted(
                        p.name
                        for p in (assets_dir / "images").iterdir()
                        if p.is_file()
                    ) if (assets_dir / "images").exists() else [],
                },
                report={},
                started_at=datetime.now(timezone.utc),
            )
            session.add(build_run)
            await session.commit()

        ctx = BuildContext(
            tenant_id=tenant_id,
            assets_dir=assets_dir,
            dry_run=dry_run,
            session=session,
            build_run_id=build_run_id,
            catalog_source=catalog_source,
        )

        try:
            if catalog_source == "api":
                await _api_catalog_pipeline(ctx, tenant.name)
            else:
                await _agent_loop(ctx)
        except Exception as exc:
            logger.exception("Builder agent loop failed for tenant=%s", tenant_id)
            ctx.report.errors.append(str(exc))
            from sqlalchemy import update
            build_run_filter = [BuildRun.tenant_id == tenant_id, BuildRun.status == "running"]
            if build_run_id:
                build_run_filter.append(BuildRun.id == build_run_id)
            await session.execute(
                update(BuildRun)
                .where(*build_run_filter)
                .values(
                    status="failed",
                    error=str(exc),
                    report=ctx.report.to_dict(),
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(
                update(Agent)
                .where(Agent.tenant_id == tenant_id)
                .values(status="failed")
            )
            await session.commit()

    return ctx.report


async def _update_build_progress(
    ctx: BuildContext,
    *,
    step: str,
    progress_pct: int,
) -> None:
    if not ctx.build_run_id:
        return
    from sqlalchemy import update

    report = dict((await _load_build_report(ctx)) or {})
    report["ui_progress_pct"] = progress_pct
    report["ui_current_step"] = step
    await ctx.session.execute(
        update(BuildRun)
        .where(
            BuildRun.id == ctx.build_run_id,
            BuildRun.tenant_id == ctx.tenant_id,
        )
        .values(report=report)
    )
    await ctx.session.commit()


async def _load_build_report(ctx: BuildContext) -> dict | None:
    if not ctx.build_run_id:
        return None
    result = await ctx.session.execute(
        select(BuildRun.report).where(
            BuildRun.id == ctx.build_run_id,
            BuildRun.tenant_id == ctx.tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    return dict(row) if row else None


async def _backfill_tenant_product_images(ctx: BuildContext) -> None:
    """Resolve Supabase Storage URLs for owner-uploaded products before indexing."""
    from app.core.product_images import backfill_product_image_row
    from app.core.schema import Product, ProductImage

    products_result = await ctx.session.execute(
        select(Product).where(Product.tenant_id == ctx.tenant_id)
    )
    products = products_result.scalars().all()
    for product in products:
        image_result = await ctx.session.execute(
            select(ProductImage)
            .where(ProductImage.product_id == product.id)
            .order_by(ProductImage.created_at.asc())
        )
        image_row = image_result.scalars().first()
        if image_row is None:
            continue
        storage_path, public_url = backfill_product_image_row(
            tenant_id=ctx.tenant_id,
            stable_key=product.stable_key,
            storage_path=image_row.storage_path,
            public_url=image_row.public_url,
            filename_hint=image_row.storage_path.rsplit("/", 1)[-1] if image_row.storage_path else None,
        )
        if storage_path:
            image_row.storage_path = storage_path
        if public_url:
            image_row.public_url = public_url
    await ctx.session.commit()


async def _api_catalog_pipeline(ctx: BuildContext, business_name: str) -> None:
    """Deterministic build for onboarding: catalog already lives in Postgres."""
    from app.builder.tools.finalize import finalize_build
    from app.builder.tools.knowledge import (
        generate_system_prompt,
        index_embeddings,
    )
    from app.builder.validation import run_self_test
    from app.core.schema import BusinessInfo, Product

    products_result = await ctx.session.execute(
        select(Product).where(Product.tenant_id == ctx.tenant_id)
    )
    products = products_result.scalars().all()
    if not products:
        raise ValueError("No products found for tenant — add products before building")

    bi_result = await ctx.session.execute(
        select(BusinessInfo).where(BusinessInfo.tenant_id == ctx.tenant_id)
    )
    for bi in bi_result.scalars().all():
        from app.builder.context import BusinessInfoItem

        ctx.business_info_items.append(
            BusinessInfoItem(
                topic=bi.topic,
                content_he=bi.content_he or "",
                content_en=bi.content_en or "",
            )
        )

    await _update_build_progress(ctx, step="collect_assets", progress_pct=15)
    await _backfill_tenant_product_images(ctx)

    categories = sorted({p.category for p in products if p.category})
    draft = (
        f"{business_name}: {len(products)} products across {', '.join(categories) or 'general'}."
    )
    await _update_build_progress(ctx, step="caption_images", progress_pct=40)
    await generate_system_prompt(ctx, draft)

    await _update_build_progress(ctx, step="index_embeddings", progress_pct=70)
    await index_embeddings(ctx)

    await _update_build_progress(ctx, step="run_self_test", progress_pct=90)
    await run_self_test(ctx)

    await _update_build_progress(ctx, step="finalize", progress_pct=98)
    await finalize_build(ctx)


async def _agent_loop(ctx: BuildContext) -> None:
    """Anthropic tool-calling loop."""
    model_cfg = get_model("builder")
    client = _get_anthropic()

    messages = [
        {
            "role": "user",
            "content": (
                f"Build the WhatsApp agent for tenant '{ctx.tenant_id}'. "
                f"Assets directory: {ctx.assets_dir}. "
                f"Dry-run mode: {ctx.dry_run}. "
                "Start by calling list_uploaded_assets to see the catalog, then proceed."
            ),
        }
    ]

    for iteration in range(MAX_ITERATIONS):
        def _call(msgs=messages):
            lf = get_langfuse()
            obs_ctx = (
                lf.start_as_current_observation(
                    name="builder-llm",
                    as_type="generation",
                    model=model_cfg.name,
                    model_parameters={
                        "temperature": model_cfg.temperature or 0.2,
                        "max_tokens": model_cfg.max_tokens or 4096,
                    },
                )
                if lf is not None
                else nullcontext()
            )
            with obs_ctx:
                resp = client.messages.create(
                    model=model_cfg.name,
                    max_tokens=model_cfg.max_tokens or 4096,
                    temperature=model_cfg.temperature or 0.2,
                    system=_CACHED_SYSTEM,
                    tools=TOOL_SCHEMAS,
                    messages=msgs,
                )
                if lf is not None:
                    try:
                        lf.update_current_generation(
                            usage_details={
                                "input": resp.usage.input_tokens,
                                "output": resp.usage.output_tokens,
                            }
                        )
                    except Exception:
                        pass
            return resp

        response = await asyncio.to_thread(_call)
        logger.debug("builder loop iter=%d stop_reason=%s", iteration, response.stop_reason)

        # Append assistant message.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            logger.info("Builder agent finished (end_turn) after %d iterations", iteration + 1)
            break

        if response.stop_reason != "tool_use":
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

        # Process all tool calls in this response.
        tool_results = []
        finalized = False
        for block in response.content:
            if block.type != "tool_use":
                continue
            result_text = await dispatch(ctx, block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })
            if block.name == "finalize_build":
                finalized = True

        messages.append({"role": "user", "content": tool_results})

        if finalized:
            logger.info("Builder finalized after %d iterations", iteration + 1)
            break
    else:
        logger.warning("Builder hit MAX_ITERATIONS=%d safety cap", MAX_ITERATIONS)
        ctx.report.errors.append(f"Build hit iteration cap ({MAX_ITERATIONS}); finalize_build may not have been called")
