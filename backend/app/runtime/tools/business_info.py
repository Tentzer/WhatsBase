"""get_business_info tool — reads the tenant's business_info rows."""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.observability import observe
from app.core.schema import BusinessInfo
from app.runtime.context import TurnContext


@observe(name="runtime.tool.get_business_info")
async def run(ctx: TurnContext, topic: str | None = None, **_ignored: object) -> str:
    async with SessionLocal() as session:
        stmt = select(BusinessInfo).where(BusinessInfo.tenant_id == ctx.tenant_id)
        if topic:
            stmt = stmt.where(BusinessInfo.topic == topic)
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return "No business information is available for that topic."

    lines: list[str] = []
    for row in rows:
        he = (row.content_he or "").strip()
        en = (row.content_en or "").strip()
        body = " | ".join(part for part in (en, he) if part)
        lines.append(f"[{row.topic}] {body}")
    return "\n".join(lines)
