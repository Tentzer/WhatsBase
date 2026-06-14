"""Update API-facing build_run progress while the Builder agent runs."""

from __future__ import annotations

from app.builder.context import BuildContext
from app.core.schema import BuildRun

TOOL_UI_PROGRESS: dict[str, tuple[str, int]] = {
    "list_uploaded_assets": ("collect_assets", 15),
    "add_business_info": ("caption_images", 60),
    "generate_system_prompt": ("index_embeddings", 70),
    "index_embeddings": ("index_embeddings", 80),
    "run_self_test": ("run_self_test", 90),
    "finalize_build": ("finalize", 98),
}

_CAPTION_PHASE_START = 15
_CAPTION_PHASE_SPAN = 45  # 15% → 60% while products are captioned/upserted


async def update_ui_progress(ctx: BuildContext, tool_name: str) -> None:
    if not ctx.build_run_id:
        return
    row = await ctx.session.get(BuildRun, ctx.build_run_id)
    if row is None:
        return
    if row.status in {"passed", "failed"}:
        return

    report = dict(row.report or {})
    current_pct = int(report.get("ui_progress_pct", 0))

    if tool_name == "list_uploaded_assets" and ctx.assets:
        report["total_products"] = len(ctx.assets)

    if tool_name == "create_or_update_product":
        done = int(report.get("products_processed", 0)) + 1
        report["products_processed"] = done
        total = max(int(report.get("total_products", 0)), done, 1)
        pct = _CAPTION_PHASE_START + int((done / total) * _CAPTION_PHASE_SPAN)
        step = "caption_images"
    elif tool_name == "caption_image":
        done = int(report.get("products_processed", 0))
        total = max(int(report.get("total_products", 0)), done + 1, 1)
        pct = _CAPTION_PHASE_START + int(((done + 1) / total) * _CAPTION_PHASE_SPAN)
        step = "caption_images"
    else:
        step_pct = TOOL_UI_PROGRESS.get(tool_name)
        if step_pct is None:
            return
        step, pct = step_pct

    report["ui_progress_pct"] = max(current_pct, pct)
    report["ui_current_step"] = step
    row.report = report
    row.status = "running"
    await ctx.session.commit()
