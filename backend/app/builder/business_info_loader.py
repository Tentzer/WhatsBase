"""Load owner business_info into the Builder context — do not rely on the LLM alone."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select

from app.builder.context import BuildContext, BusinessInfoItem
from app.core.schema import BusinessInfo

logger = logging.getLogger(__name__)

_VALID_TOPICS = frozenset({"hours", "location", "policy", "faq", "other"})


def parse_business_info_txt(path: Path) -> list[BusinessInfoItem]:
    """Parse business_info.txt (TOPIC | HE | EN per line)."""
    if not path.exists():
        return []

    items: list[BusinessInfoItem] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            continue
        topic = parts[0].lower()
        if topic not in _VALID_TOPICS:
            topic = "other"
        content_he = parts[1]
        content_en = parts[2]
        if not content_he and not content_en:
            continue
        items.append(
            BusinessInfoItem(
                topic=topic,
                content_he=content_he,
                content_en=content_en,
            )
        )
    return items


def _item_key(item: BusinessInfoItem) -> tuple[str, str, str]:
    return (item.topic, item.content_he, item.content_en)


def merge_business_info_items(
    existing: list[BusinessInfoItem],
    incoming: list[BusinessInfoItem],
) -> list[BusinessInfoItem]:
    """Append incoming items, skipping exact duplicates."""
    seen = {_item_key(item) for item in existing}
    merged = list(existing)
    for item in incoming:
        key = _item_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


async def ensure_business_info_loaded(ctx: BuildContext) -> int:
    """Seed ctx.business_info_items from business_info.txt, then DB if still empty."""
    from_file = parse_business_info_txt(ctx.assets_dir / "business_info.txt")
    if from_file:
        before = len(ctx.business_info_items)
        ctx.business_info_items = merge_business_info_items(ctx.business_info_items, from_file)
        added = len(ctx.business_info_items) - before
        if added:
            logger.info(
                "loaded %d business_info record(s) from file for tenant=%s",
                added,
                ctx.tenant_id,
            )

    if ctx.business_info_items:
        return len(ctx.business_info_items)

    result = await ctx.session.execute(
        select(BusinessInfo)
        .where(BusinessInfo.tenant_id == ctx.tenant_id)
        .order_by(BusinessInfo.created_at.asc())
    )
    rows = result.scalars().all()
    if not rows:
        return 0

    from_db = [
        BusinessInfoItem(
            topic=row.topic,
            content_he=row.content_he or "",
            content_en=row.content_en or "",
        )
        for row in rows
        if (row.content_he or "").strip() or (row.content_en or "").strip()
    ]
    before = len(ctx.business_info_items)
    ctx.business_info_items = merge_business_info_items(ctx.business_info_items, from_db)
    added = len(ctx.business_info_items) - before
    if added:
        logger.info(
            "loaded %d business_info record(s) from DB for tenant=%s",
            added,
            ctx.tenant_id,
        )
    return len(ctx.business_info_items)
