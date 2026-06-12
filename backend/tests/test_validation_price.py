"""Unit tests for _normalize_price — no DB, no LLM."""

import pytest

from app.builder.validation import _normalize_price


@pytest.mark.parametrize("raw", [
    "₪4,990",
    "4,990 ₪",
    "The price is ₪4,990.",
    "4990",
])
def test_normalize_price_contains_digits(raw):
    assert "4990" in _normalize_price(raw), f"'4990' not found in _normalize_price({raw!r})"
