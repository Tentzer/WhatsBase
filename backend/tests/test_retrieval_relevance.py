"""Relevance filtering for retrieval hits."""

from decimal import Decimal

from app.retrieval.relevance import (
    filter_relevant_hits,
    hits_mentioned_in_reply,
    infer_query_filters,
    select_card_hits,
)
from app.retrieval.types import ProductHit


def _hit(
    *,
    product_id: str,
    name_en: str,
    colors: list[str] | None = None,
    score: float,
) -> ProductHit:
    return ProductHit(
        product_id=product_id,
        stable_key=product_id,
        name_he=None,
        name_en=name_en,
        description_he=None,
        description_en=None,
        category="sofa",
        price=Decimal("1000"),
        currency="ILS",
        in_stock=True,
        colors=colors or [],
        image_urls=[],
        score=score,
    )


def test_infer_white_sofa_filters():
    filters = infer_query_filters("Do you have a white sofa?")
    assert filters["colors"] == ["white"]
    assert filters["category"] == "sofa"


def test_filter_drops_cream_for_white_query():
    hits = [
        _hit(product_id="1", name_en="White 3-Seat Sofa", colors=["white"], score=0.9),
        _hit(product_id="2", name_en="White 3-Seater Sofa", colors=["white"], score=0.85),
        _hit(product_id="3", name_en="Cream 2-Seat Sofa", colors=["cream"], score=0.8),
    ]
    filtered = filter_relevant_hits("white sofa", hits)
    names = [h.name_en for h in filtered]
    assert "Cream 2-Seat Sofa" not in names
    assert len(filtered) == 2


def test_select_cards_follows_reply_mentions():
    hits = [
        _hit(product_id="1", name_en="White 3-Seat Sofa", colors=["white"], score=0.9),
        _hit(product_id="2", name_en="White 3-Seater Sofa", colors=["white"], score=0.85),
    ]
    reply = "Yes! **White 3-Seat Sofa** is ₪4,990 and **White 3-Seater Sofa** is ₪3,990."
    cards = select_card_hits("white sofa", reply, hits)
    assert len(cards) == 2
    assert hits_mentioned_in_reply(reply, hits)[0].name_en == "White 3-Seat Sofa"
