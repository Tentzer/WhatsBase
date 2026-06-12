"""Builder tool: finalize_build — the hard gate."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import update

from app.builder.context import BuildContext
from app.core.schema import Agent, BuildRun

logger = logging.getLogger(__name__)


async def finalize_build(ctx: BuildContext) -> str:
    """Finalize the build. GATE: raises if self-test has not passed this run."""
    if ctx.dry_run:
        logger.info("[dry-run] would finalize build — skipping DB writes")
        return json.dumps({"status": "passed", "agent": "live (dry-run only)", "dry_run": True})

    session = ctx.session

    if not ctx.self_test_passed:
        # Record failure.
        await _set_status(session, ctx, status="failed")
        failed_qs = [
            q for q in ctx.report.self_test.get("questions", [])
            if not q.get("ok")
        ]
        msg = (
            f"Build rejected: self-test failed "
            f"({len(failed_qs)} question(s) did not pass). "
            f"Call run_self_test first and ensure all 8 questions pass."
        )
        logger.warning(msg)
        return json.dumps({"status": "failed", "reason": msg,
                           "failed_questions": [q["q"] for q in failed_qs]})

    # Gate passed — mark agent live.
    await _set_status(session, ctx, status="passed")
    logger.info("finalize_build: agent is LIVE for tenant=%s", ctx.tenant_id)
    return json.dumps({"status": "passed", "agent": "live"})


async def _set_status(session, ctx: BuildContext, status: str) -> None:
    agent_status = "live" if status == "passed" else "failed"

    await session.execute(
        update(Agent)
        .where(Agent.tenant_id == ctx.tenant_id)
        .values(status=agent_status)
    )

    report_dict = ctx.report.to_dict()
    report_dict["self_test"]["passed"] = ctx.self_test_passed

    await session.execute(
        update(BuildRun)
        .where(
            BuildRun.tenant_id == ctx.tenant_id,
            BuildRun.status == "running",
        )
        .values(
            status=status,
            report=report_dict,
            finished_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
