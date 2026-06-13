"""search_products tool — hybrid catalog retrieval, always tenant-scoped."""

from __future__ import annotations

from app.core.observability import observe
from app.retrieval.search import search as retrieval_search
from app.retrieval.types import ProductHit
from app.runtime.context import TurnContext


def _format_hits(hits: list[ProductHit]) -> str:
    lines: list[str] = []
    for hit in hits:
        name = hit.name_en or hit.name_he or "(unnamed)"
        price = f"{float(hit.price)} {hit.currency}" if hit.price is not None else "unknown"
        stock = "in_stock" if hit.in_stock else "out_of_stock"
        lines.append(
            f"- id={hit.product_id}; name_en={hit.name_en or ''}; name_he={hit.name_he or ''}; "
            f"category={hit.category or ''}; price={price}; stock={stock}"
        )
    return "Matching products:\n" + "\n".join(lines)


@observe(name="runtime.tool.search_products")
async def run(
    ctx: TurnContext,
    query: str,
    category: str | None = None,
    in_stock: bool | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    **_ignored: object,
) -> str:
    filters: dict = {}
    if category is not None:
        filters["category"] = category
    if in_stock is not None:
        filters["in_stock"] = in_stock
    if price_min is not None:
        filters["price_min"] = price_min
    if price_max is not None:
        filters["price_max"] = price_max

    hits = await retrieval_search(
        tenant_id=ctx.tenant_id, query=query, filters=filters or None, k=5
    )

    # Cache hits so send_product_cards can build cards by id, and record prices
    # so the price guardrail knows which figures are tool-backed.
    for hit in hits:
        ctx.hits_by_id[str(hit.product_id)] = hit
        if hit.price is not None:
            ctx.tool_prices.add(round(float(hit.price), 2))

    if not hits:
        return "No matching products found in this catalog."
    return _format_hits(hits)
