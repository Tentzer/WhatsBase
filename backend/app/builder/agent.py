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
async def run_build(tenant_id: str, assets_dir: Path, dry_run: bool = False) -> BuildReport:
    """Run the full Builder agent for one tenant. Returns the BuildReport."""
    update_trace(tenant_id=tenant_id)

    async with SessionLocal() as session:
        # Verify tenant exists.
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found in database")

        # Create a build_runs row (running).
        build_run = BuildRun(
            tenant_id=tenant_id,
            status="running",
            input_manifest={
                "assets_dir": str(assets_dir),
                "dry_run": dry_run,
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
        )

        try:
            await _agent_loop(ctx)
        except Exception as exc:
            logger.exception("Builder agent loop failed for tenant=%s", tenant_id)
            ctx.report.errors.append(str(exc))
            # Mark build failed if not already handled by finalize_build.
            from sqlalchemy import update
            await session.execute(
                update(BuildRun)
                .where(BuildRun.tenant_id == tenant_id, BuildRun.status == "running")
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
