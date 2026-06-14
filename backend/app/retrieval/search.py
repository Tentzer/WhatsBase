"""Hybrid retrieval: pgvector cosine + JSONB metadata filter pushdown.

Always scoped by tenant_id. The DATABASE_URL connects as the Postgres owner
role (bypasses RLS), so the explicit WHERE tenant_id = :tenant_id is the ONLY
enforcement layer here. Never make tenant_id optional.
"""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.observability import observe, update_trace
from app.retrieval.embed import embed_query
from app.retrieval.types import ProductHit


@observe(name="retrieval.search")
async def search(
    tenant_id: str,
    query: str,
    filters: dict | None = None,
    k: int = 3,
) -> list[ProductHit]:
    """Return top-k ProductHits for query, scoped to tenant_id.

    filters keys (all optional):
      category    str   — exact match via JSONB containment
      colors      list  — containment: any color must appear in metadata.colors
      in_stock    bool  — exact match
      price_min   float — lower bound (inclusive)
      price_max   float — upper bound (inclusive)
      ref_type    str   — 'product' (default) or 'business_info'
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for retrieval.search")

    update_trace(tenant_id=tenant_id)

    filters = filters or {}
    ref_type = filters.get("ref_type", "product")

    qvec = await embed_query(query)

    # Build WHERE clauses dynamically.
    where_clauses = [
        "e.tenant_id = :tenant_id",
        "e.status = 'active'",
        "e.ref_type = :ref_type",
    ]
    params: dict = {
        "tenant_id": tenant_id,
        "ref_type": ref_type,
        "qvec": f"[{','.join(str(v) for v in qvec)}]",
        "k": k,
    }

    if "category" in filters:
        where_clauses.append("e.metadata @> CAST(:cat_filter AS jsonb)")
        params["cat_filter"] = json.dumps({"category": filters["category"]})

    if "in_stock" in filters:
        where_clauses.append("e.metadata @> CAST(:stock_filter AS jsonb)")
        params["stock_filter"] = json.dumps({"in_stock": filters["in_stock"]})

    if "colors" in filters:
        # Any of the requested colors must appear in metadata.colors array.
        for i, color in enumerate(filters["colors"]):
            where_clauses.append(f"e.metadata @> CAST(:color_filter_{i} AS jsonb)")
            params[f"color_filter_{i}"] = json.dumps({"colors": [color]})

    if "price_min" in filters:
        where_clauses.append("(e.metadata->>'price')::numeric >= :price_min")
        params["price_min"] = filters["price_min"]

    if "price_max" in filters:
        where_clauses.append("(e.metadata->>'price')::numeric <= :price_max")
        params["price_max"] = filters["price_max"]

    where_sql = " AND ".join(where_clauses)

    stmt = text(f"""
        SELECT
            p.id                        AS product_id,
            p.stable_key,
            p.name_he,
            p.name_en,
            p.description_he,
            p.description_en,
            p.category,
            p.price,
            p.currency,
            p.in_stock,
            COALESCE(
                json_agg(pi.public_url ORDER BY pi.id)
                    FILTER (WHERE pi.public_url IS NOT NULL),
                '[]'::json
            )                           AS image_urls,
            1 - (e.vector <=> CAST(:qvec AS halfvec))  AS score
        FROM embeddings e
        JOIN products p
            ON p.id = e.ref_id
            AND p.tenant_id = :tenant_id
        LEFT JOIN product_images pi
            ON pi.product_id = p.id
        WHERE {where_sql}
        GROUP BY
            p.id, p.stable_key, p.name_he, p.name_en,
            p.description_he, p.description_en,
            p.category, p.price, p.currency, p.in_stock,
            e.vector, e.id
        ORDER BY e.vector <=> CAST(:qvec AS halfvec)
        LIMIT :k
    """)

    async with SessionLocal() as session:
        result = await session.execute(stmt, params)
        rows = result.mappings().all()

    hits: list[ProductHit] = []
    for row in rows:
        image_urls = row["image_urls"]
        if isinstance(image_urls, str):
            image_urls = json.loads(image_urls)

        hits.append(
            ProductHit(
                product_id=str(row["product_id"]),
                stable_key=row["stable_key"] or "",
                name_he=row["name_he"],
                name_en=row["name_en"],
                description_he=row["description_he"],
                description_en=row["description_en"],
                category=row["category"],
                price=Decimal(str(row["price"])) if row["price"] is not None else None,
                currency=row["currency"] or "ILS",
                in_stock=bool(row["in_stock"]),
                image_urls=image_urls or [],
                score=float(row["score"]),
            )
        )

    return hits
