"""Tool-level tests for the conversation runtime (no credentials / no DB).

DB-touching tools have their SessionLocal monkeypatched; the cached card path
and the missing-tenant guard need neither DB nor keys.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.retrieval.types import ProductHit
from app.runtime import tools
from app.runtime.context import TurnContext
from app.runtime.tools import business_info, handoff, product_cards


def _hit(pid="p1"):
    return ProductHit(
        product_id=pid,
        stable_key="SOF-001",
        name_he="ספה לבנה",
        name_en="White Sofa",
        description_he=None,
        description_en=None,
        category="sofa",
        price=Decimal("4990"),
        currency="ILS",
        in_stock=True,
        image_urls=["https://img/sofa.jpg"],
        score=0.9,
    )


# --- fake async session for DB-touching tools --------------------------------
class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.executed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *a, **k):
        self.executed += 1
        return _Result(self._rows)

    async def commit(self):
        pass


# --- retrieval tenant enforcement (search.py:38) -----------------------------
@pytest.mark.asyncio
async def test_search_requires_tenant_id():
    from app.retrieval.search import search

    with pytest.raises(ValueError):
        await search("", "white sofa")  # raises before any embedding/SQL


# --- dispatch ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_unknown_tool():
    out = await tools.dispatch("does_not_exist", {}, TurnContext(tenant_id="t1"))
    assert "Unknown tool" in out


# --- get_business_info -------------------------------------------------------
@pytest.mark.asyncio
async def test_business_info_formats_rows(monkeypatch):
    rows = [SimpleNamespace(topic="hours", content_he="א-ה 9-18", content_en="Sun-Thu 9-18")]
    monkeypatch.setattr(business_info, "SessionLocal", lambda: _Session(rows))
    out = await business_info.run(TurnContext(tenant_id="t1"), topic="hours")
    assert "hours" in out and "Sun-Thu 9-18" in out


@pytest.mark.asyncio
async def test_business_info_empty(monkeypatch):
    monkeypatch.setattr(business_info, "SessionLocal", lambda: _Session([]))
    out = await business_info.run(TurnContext(tenant_id="t1"))
    assert "No business information" in out


# --- send_product_cards (cached path, test-chat channel = no enqueue) --------
@pytest.mark.asyncio
async def test_send_product_cards_cached_records_without_enqueue():
    ctx = TurnContext(tenant_id="t1", channel="test_chat")
    ctx.hits_by_id["p1"] = _hit("p1")
    out = await product_cards.run(ctx, product_ids=["p1"])
    assert len(ctx.cards) == 1
    assert ctx.cards[0].name_en == "White Sofa"
    assert "1" in out


@pytest.mark.asyncio
async def test_send_product_cards_unknown_id(monkeypatch):
    # Not cached → DB fallback; stub it empty so no DB is touched.
    ctx = TurnContext(tenant_id="t1", channel="test_chat")

    async def _empty_fetch(tenant_id, ids):
        return {}

    monkeypatch.setattr(product_cards, "_fetch_cards", _empty_fetch)
    out = await product_cards.run(ctx, product_ids=["nope"])
    assert "Could not find" in out
    assert ctx.cards == []


# --- handoff_to_human --------------------------------------------------------
@pytest.mark.asyncio
async def test_handoff_sets_flag_no_conversation():
    ctx = TurnContext(tenant_id="t1", conversation_id=None)
    out = await handoff.run(ctx, reason="customer is angry")
    assert ctx.handoff is True
    assert ctx.handoff_reason == "customer is angry"
    assert "human" in out.lower()
