from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ProductHit:
    product_id: str
    stable_key: str
    name_he: str | None
    name_en: str | None
    description_he: str | None
    description_en: str | None
    category: str | None
    price: Decimal | None
    currency: str
    in_stock: bool
    colors: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    score: float = 0.0  # cosine similarity = 1 - cosine_distance
