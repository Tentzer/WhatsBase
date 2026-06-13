"""Channel-agnostic value types for a conversation turn.

Kept free of any FastAPI/`api` import so the arq worker can use the runtime
without pulling in the web layer. The REST endpoint maps `ProductCard` onto its
own `ProductCardResponse` schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProductCard:
    """A product the agent chose to show the customer (photo + name + price)."""

    id: str
    image_url: str | None
    name_he: str
    name_en: str
    price: float
    currency: str


@dataclass
class TurnResult:
    """The outcome of one agent turn, consumed by either the WhatsApp worker or
    the REST test-chat endpoint."""

    reply_text: str
    cards: list[ProductCard] = field(default_factory=list)
    handoff: bool = False
    trace_id: str | None = None
