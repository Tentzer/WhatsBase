"""Update API-facing build_run progress while the Builder agent runs."""

from __future__ import annotations

from sqlalchemy import update

from app.builder.context import BuildContext
from app.core.schema import BuildRun

TOOL_UI_PROGRESS: dict[str, tuple[str, int]] = {
    "list_uploaded_assets": ("collect_assets", 15),
    "caption_image": ("caption_images", 40),
    "create_or_update_product": ("caption_images", 55),
    "add_business_info": ("caption_images", 60),
    "generate_system_prompt": ("index_embeddings", 70),
    "index_embeddings": ("index_embeddings", 80),
    "run_self_test": ("run_self_test", 90),
    "finalize_build": ("finalize", 98),
}


async def update_ui_progress(ctx: BuildContext, tool_name: str) -> None:
    if not ctx.build_run_id:
        return
    step_pct = TOOL_UI_PROGRESS.get(tool_name)
    if step_pct is None:
        return
    step, pct = step_pct
    row = await ctx.session.get(BuildRun, ctx.build_run_id)
    if row is None:
        return
    report = dict(row.report or {})
    report["ui_progress_pct"] = pct
    report["ui_current_step"] = step
    row.report = report
    row.status = "running"
    await ctx.session.commit()
