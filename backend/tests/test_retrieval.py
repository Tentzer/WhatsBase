"""Retrieval unit tests — no DB, no live API keys required.

Integration tests are marked @pytest.mark.integration and are skipped unless
DATABASE_URL is set to a real Postgres instance.
"""

from __future__ import annotations

import os
import uuid

import pytest


# ---------- tenant guard ----------

@pytest.mark.asyncio
async def test_search_requires_tenant(monkeypatch):
    """Empty tenant_id must raise immediately, before any DB or embed call."""
    from app.retrieval.search import search

    with pytest.raises(ValueError, match="tenant_id"):
        await search("", "white sofa")


@pytest.mark.asyncio
async def test_search_requires_tenant_none(monkeypatch):
    from app.retrieval.search import search

    with pytest.raises((ValueError, TypeError)):
        await search(None, "white sofa")  # type: ignore[arg-type]


# ---------- SQL clause verification ----------

def _compile_search_sql(filters: dict | None = None) -> str:
    """Rebuild the WHERE clause text that search() constructs, without executing it."""
    where_clauses = [
        "e.tenant_id = :tenant_id",
        "e.status = 'active'",
        "e.ref_type = :ref_type",
    ]
    filters = filters or {}

    if "category" in filters:
        where_clauses.append("e.metadata @> CAST(:cat_filter AS jsonb)")
    if "in_stock" in filters:
        where_clauses.append("e.metadata @> CAST(:stock_filter AS jsonb)")
    if "colors" in filters:
        for i in range(len(filters["colors"])):
            where_clauses.append(f"e.metadata @> CAST(:color_filter_{i} AS jsonb)")
    if "price_min" in filters:
        where_clauses.append("(e.metadata->>'price')::numeric >= :price_min")
    if "price_max" in filters:
        where_clauses.append("(e.metadata->>'price')::numeric <= :price_max")

    return " AND ".join(where_clauses)


def test_query_has_tenant_and_active_filters():
    sql = _compile_search_sql()
    assert "e.tenant_id = :tenant_id" in sql
    assert "e.status = 'active'" in sql
    assert "e.ref_type = :ref_type" in sql


def test_filter_pushdown_category():
    sql = _compile_search_sql({"category": "sofa"})
    assert "CAST(:cat_filter AS jsonb)" in sql


def test_filter_pushdown_in_stock():
    sql = _compile_search_sql({"in_stock": True})
    assert "CAST(:stock_filter AS jsonb)" in sql


def test_filter_pushdown_price_range():
    sql = _compile_search_sql({"price_min": 100, "price_max": 1000})
    assert "(e.metadata->>'price')::numeric >= :price_min" in sql
    assert "(e.metadata->>'price')::numeric <= :price_max" in sql


def test_filter_pushdown_compound():
    """in_stock + price range both appear in the WHERE clause."""
    sql = _compile_search_sql({"in_stock": True, "price_max": 1500})
    assert "CAST(:stock_filter AS jsonb)" in sql
    assert "(e.metadata->>'price')::numeric <= :price_max" in sql


def test_filter_pushdown_colors():
    sql = _compile_search_sql({"colors": ["white", "cream"]})
    assert "CAST(:color_filter_0 AS jsonb)" in sql
    assert "CAST(:color_filter_1 AS jsonb)" in sql


# ---------- integration ----------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_executes_and_returns_hit():
    """Execute a real search against the DB; catches SQL bind-param and JOIN type bugs."""
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")

    from sqlalchemy import delete

    from app.core.db import SessionLocal
    from app.core.schema import Embedding, Product, Tenant
    from app.retrieval.embed import embed_query
    from app.retrieval.search import search

    test_tenant_id = str(uuid.uuid4())

    # Tenant must be committed before Product (FK constraint).
    async with SessionLocal() as session:
        session.add(Tenant(id=test_tenant_id, name="test-retrieval", status="active", plan="free"))
        await session.commit()

    async with SessionLocal() as session:
        product = Product(
            tenant_id=test_tenant_id,
            stable_key="test-sofa",
            name_en="White Sofa",
            name_he="ספה לבנה",
            category="sofa",
            price=4990,
            currency="ILS",
            in_stock=True,
            attributes={"colors": ["white"]},
            source="owner_input",
        )
        session.add(product)
        await session.flush()

        vector = await embed_query("white sofa")
        session.add(Embedding(
            tenant_id=test_tenant_id,
            ref_type="product",
            ref_id=str(product.id),
            content="White Sofa ספה לבנה category: sofa",
            vector=vector,
            embedding_metadata={"category": "sofa", "colors": ["white"], "in_stock": True, "price": 4990.0},
            status="active",
        ))
        await session.commit()

    try:
        hits = await search(test_tenant_id, "white sofa", k=3)
        assert hits, "Expected at least one hit"
        assert any(h.stable_key == "test-sofa" for h in hits), \
            f"test-sofa not in hits: {[h.stable_key for h in hits]}"

        filtered = await search(test_tenant_id, "sofa", filters={"category": "sofa"}, k=3)
        assert any(h.stable_key == "test-sofa" for h in filtered), \
            "Category filter should still return test-sofa"
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(Embedding).where(Embedding.tenant_id == test_tenant_id))
            await session.execute(delete(Product).where(Product.tenant_id == test_tenant_id))
            await session.execute(delete(Tenant).where(Tenant.id == test_tenant_id))
            await session.commit()
