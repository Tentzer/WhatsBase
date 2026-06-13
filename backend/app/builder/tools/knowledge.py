"""Builder tools: add_business_info, generate_system_prompt, index_embeddings."""

from __future__ import annotations

import json
import logging

from sqlalchemy import delete, select, text, update

from app.builder.context import BuildContext, BusinessInfoItem
from app.builder.prompts import render_conversation_prompt
from app.core.schema import Agent, BusinessInfo, Embedding, Product, Tenant

logger = logging.getLogger(__name__)


async def add_business_info(ctx: BuildContext, topic: str, content_he: str, content_en: str) -> str:
    """Accumulate a business_info record. Written to DB during index_embeddings."""
    item = BusinessInfoItem(topic=topic, content_he=content_he, content_en=content_en)
    ctx.business_info_items.append(item)
    ctx.report.business_info.append(f"{topic}: {content_en[:60]}")
    logger.info("queued business_info: topic=%s", topic)
    return json.dumps({"status": "queued", "topic": topic})


async def generate_system_prompt(ctx: BuildContext, draft: str) -> str:
    """Compose and persist the tenant's system prompt from the build draft."""
    session = ctx.session

    # Get business name + description from tenant row.
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == ctx.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    business_name = tenant.name if tenant and tenant.name else "the business"

    # Tenant.description drives identity. Trailing space when present so the
    # opening sentence flows; empty string when null/blank (graceful degrade).
    raw_desc = ((tenant.description if tenant else None) or "").strip()
    business_description = f"{raw_desc} " if raw_desc else ""

    # Bilingual business info: feed BOTH languages so the agent answers
    # hours/location/policy idiomatically in either. Per-field fallback when
    # only one language is present.
    biz_lines = []
    for item in ctx.business_info_items:
        en = (item.content_en or "").strip()
        he = (item.content_he or "").strip()
        biz_lines.append(f"  [{item.topic}]")
        if en:
            biz_lines.append(f"    EN: {en}")
        if he:
            biz_lines.append(f"    HE: {he}")
    business_summary = "\n".join(biz_lines) if biz_lines else "(no business info provided)"

    # Summarize catalog from products already in DB.
    products_result = await session.execute(
        select(Product).where(Product.tenant_id == ctx.tenant_id)
    )
    products = products_result.scalars().all()
    categories = sorted({p.category for p in products if p.category})
    catalog_summary = (
        f"{len(products)} products across categories: {', '.join(categories)}"
        if categories
        else f"{len(products)} products."
    )

    # A few real product names ground the catalog without hardcoding examples.
    sample_names = [n for n in
                    ((p.name_en or p.name_he or "").strip() for p in products) if n][:5]
    catalog_examples = (
        f"Examples from the catalog: {', '.join(sample_names)}.\n" if sample_names else ""
    )

    # Escape literal braces so tenant free-text can't break str.format().
    def _esc(s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    system_prompt = render_conversation_prompt(
        business_name=_esc(business_name),
        business_description=_esc(business_description),
        business_summary=_esc(business_summary),
        catalog_summary=_esc(catalog_summary),
        catalog_examples=_esc(catalog_examples),
    )

    if ctx.dry_run:
        logger.info("[dry-run] would write system_prompt (%d chars) for tenant=%s",
                    len(system_prompt), ctx.tenant_id)
        return json.dumps({"status": "ok", "prompt_length": len(system_prompt), "dry_run": True})

    # Upsert agents row.
    agent_result = await session.execute(
        select(Agent).where(Agent.tenant_id == ctx.tenant_id)
    )
    agent = agent_result.scalar_one_or_none()
    if agent:
        await session.execute(
            update(Agent)
            .where(Agent.tenant_id == ctx.tenant_id)
            .values(system_prompt=system_prompt, status="building")
        )
    else:
        session.add(
            Agent(
                tenant_id=ctx.tenant_id,
                system_prompt=system_prompt,
                status="building",
            )
        )

    await session.commit()
    logger.info("generated system prompt (%d chars)", len(system_prompt))
    return json.dumps({"status": "ok", "prompt_length": len(system_prompt)})


# Metadata contract (retrieval filter pushdown depends on these exact keys+types):
#   product embeddings:     {category: str, colors: list[str], in_stock: bool, price: float}
#   business_info embeds:   {topic: str}


async def index_embeddings(ctx: BuildContext) -> str:
    """Generate and atomically swap embeddings for all products and business_info."""
    from app.retrieval.embed import embed_query

    if ctx.dry_run:
        logger.info("[dry-run] would index embeddings for tenant=%s — skipping all writes", ctx.tenant_id)
        ctx.report.embeddings = {"staged": 0, "promoted": 0, "dry_run": True}
        return json.dumps({"status": "ok", "promoted": 0, "dry_run": True})

    session = ctx.session
    tenant_id = ctx.tenant_id

    # --- Write business_info rows (delete-then-insert for idempotency) ---
    if ctx.business_info_items:
        await session.execute(
            delete(BusinessInfo).where(BusinessInfo.tenant_id == tenant_id)
        )
        for item in ctx.business_info_items:
            session.add(
                BusinessInfo(
                    tenant_id=tenant_id,
                    topic=item.topic,
                    content_he=item.content_he,
                    content_en=item.content_en,
                )
            )
        await session.flush()

    # --- Collect products ---
    products_result = await session.execute(
        select(Product).where(Product.tenant_id == tenant_id)
    )
    products = products_result.scalars().all()

    # --- Collect business_info ---
    bi_result = await session.execute(
        select(BusinessInfo).where(BusinessInfo.tenant_id == tenant_id)
    )
    business_infos = bi_result.scalars().all()

    staged = 0

    # --- Embed products as staging ---
    for product in products:
        content = _product_embedding_text(product)
        vector = await embed_query(content)

        # Locked metadata contract for retrieval filter pushdown.
        colors = product.attributes.get("colors", []) if product.attributes else []
        embedding_meta = {
            "category": product.category or "",
            "colors": colors if isinstance(colors, list) else [],
            "in_stock": bool(product.in_stock),
            "price": float(product.price) if product.price is not None else None,
        }

        session.add(
            Embedding(
                tenant_id=tenant_id,
                ref_type="product",
                ref_id=str(product.id),
                content=content,
                vector=vector,
                embedding_metadata=embedding_meta,
                status="staging",
            )
        )
        staged += 1

    # --- Embed business_info as staging ---
    for bi in business_infos:
        content = _bi_embedding_text(bi)
        vector = await embed_query(content)

        embedding_meta = {"topic": bi.topic}

        session.add(
            Embedding(
                tenant_id=tenant_id,
                ref_type="business_info",
                ref_id=str(bi.id),
                content=content,
                vector=vector,
                embedding_metadata=embedding_meta,
                status="staging",
            )
        )
        staged += 1

    await session.flush()

    # --- Atomic swap: delete active, promote staging ---
    await session.execute(
        delete(Embedding).where(
            Embedding.tenant_id == tenant_id,
            Embedding.status == "active",
        )
    )
    await session.execute(
        update(Embedding)
        .where(
            Embedding.tenant_id == tenant_id,
            Embedding.status == "staging",
        )
        .values(status="active")
    )
    await session.commit()

    ctx.report.embeddings = {"staged": staged, "promoted": staged}
    logger.info(
        "index_embeddings: promoted %d embeddings (%d products, %d business_info)",
        staged, len(products), len(business_infos),
    )
    return json.dumps({"status": "ok", "promoted": staged})


async def index_new_product_embeddings(ctx: BuildContext) -> str:
    """Embed only products that do not yet have an active embedding row.

    Skips system-prompt regeneration and leaves existing embeddings untouched —
    used when the owner adds new catalog items without changing business info.
    """
    from app.retrieval.embed import embed_query

    if ctx.dry_run:
        logger.info(
            "[dry-run] would index new product embeddings for tenant=%s — skipping",
            ctx.tenant_id,
        )
        return json.dumps({"status": "ok", "promoted": 0, "new_products": 0, "dry_run": True})

    session = ctx.session
    tenant_id = ctx.tenant_id

    products_result = await session.execute(
        select(Product).where(Product.tenant_id == tenant_id)
    )
    products = products_result.scalars().all()

    embedded_ids = {
        row
        for row in (
            await session.execute(
                select(Embedding.ref_id).where(
                    Embedding.tenant_id == tenant_id,
                    Embedding.ref_type == "product",
                    Embedding.status == "active",
                )
            )
        ).scalars().all()
    }

    new_products = [p for p in products if str(p.id) not in embedded_ids]
    if not new_products:
        logger.info("index_new_product_embeddings: no new products for tenant=%s", tenant_id)
        return json.dumps({"status": "ok", "promoted": 0, "new_products": 0})

    promoted = 0
    for product in new_products:
        content = _product_embedding_text(product)
        vector = await embed_query(content)
        colors = product.attributes.get("colors", []) if product.attributes else []
        embedding_meta = {
            "category": product.category or "",
            "colors": colors if isinstance(colors, list) else [],
            "in_stock": bool(product.in_stock),
            "price": float(product.price) if product.price is not None else None,
        }
        session.add(
            Embedding(
                tenant_id=tenant_id,
                ref_type="product",
                ref_id=str(product.id),
                content=content,
                vector=vector,
                embedding_metadata=embedding_meta,
                status="active",
            )
        )
        promoted += 1

    await session.commit()
    ctx.report.embeddings = {"staged": promoted, "promoted": promoted, "incremental": True}
    logger.info(
        "index_new_product_embeddings: added %d embeddings for tenant=%s",
        promoted,
        tenant_id,
    )
    return json.dumps({"status": "ok", "promoted": promoted, "new_products": promoted})


def _product_embedding_text(product: Product) -> str:
    parts = [
        product.name_en or "",
        product.name_he or "",
        product.description_en or "",
        product.description_he or "",
        f"category: {product.category or ''}",
    ]
    attrs = product.attributes or {}
    if attrs.get("colors"):
        parts.append(f"colors: {' '.join(attrs['colors'])}")
    if attrs.get("materials"):
        parts.append(f"materials: {' '.join(attrs['materials'])}")
    return " ".join(p for p in parts if p)


def _bi_embedding_text(bi: BusinessInfo) -> str:
    return f"{bi.content_en or ''} {bi.content_he or ''}".strip()
