"""send_product_cards tool — show specific products to the customer.

On the WhatsApp channel each card is enqueued as a `send_outgoing` image job
through the injected callable; the adapter is never called synchronously here.
On the test-chat channel there is no callable — cards are returned to the REST
layer for browser rendering. Either way the cards are recorded on the context.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.observability import observe
from app.core.schema import Product, ProductImage
from app.runtime.context import TurnContext
from app.runtime.types import ProductCard

logger = logging.getLogger(__name__)


def _caption(card: ProductCard, lang: str) -> str:
    name = (card.name_he if lang == "he" else card.name_en) or card.name_en or card.name_he
    price = f"{card.price:g} {card.currency}" if card.price else ""
    return f"{name}\n{price}".strip()


async def _fetch_cards(tenant_id: str, product_ids: list[str]) -> dict[str, ProductCard]:
    """Tenant-scoped fallback for ids not cached from this turn's searches."""
    out: dict[str, ProductCard] = {}
    if not product_ids:
        return out
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.id.in_(product_ids),
                )
            )
        ).scalars().all()
        for product in rows:
            image = (
                await session.execute(
                    select(ProductImage.public_url)
                    .where(ProductImage.product_id == product.id)
                    .order_by(ProductImage.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            out[str(product.id)] = ProductCard(
                id=str(product.id),
                image_url=image,
                name_he=product.name_he or "",
                name_en=product.name_en or "",
                price=float(product.price or 0),
                currency=product.currency or "ILS",
            )
    return out


@observe(name="runtime.tool.send_product_cards")
async def run(ctx: TurnContext, product_ids: list[str], **_ignored: object) -> str:
    ids = [str(pid) for pid in (product_ids or [])]

    cards: list[ProductCard] = []
    missing: list[str] = []
    for pid in ids:
        hit = ctx.hits_by_id.get(pid)
        if hit is None:
            missing.append(pid)
            continue
        cards.append(
            ProductCard(
                id=pid,
                image_url=hit.image_urls[0] if hit.image_urls else None,
                name_he=hit.name_he or "",
                name_en=hit.name_en or "",
                price=float(hit.price or 0),
                currency=hit.currency,
            )
        )

    if missing:
        fetched = await _fetch_cards(ctx.tenant_id, missing)
        cards.extend(fetched[pid] for pid in missing if pid in fetched)

    sent = 0
    for card in cards:
        ctx.cards.append(card)
        if card.price:
            ctx.tool_prices.add(round(card.price, 2))
        if (
            ctx.enqueue_outgoing
            and ctx.green_api_instance_id
            and ctx.chat_id
            and card.image_url
        ):
            await ctx.enqueue_outgoing(
                {
                    "green_api_instance_id": ctx.green_api_instance_id,
                    "chat_id": ctx.chat_id,
                    "type": "image",
                    "image_url": card.image_url,
                    "caption": _caption(card, ctx.lang),
                }
            )
            sent += 1

    if not cards:
        return "Could not find those product ids to show. Search again to get valid ids."
    return f"Showed {len(cards)} product card(s) to the customer."
