"""Unit tests for runtime conversation guardrails (pure, no credentials)."""

from __future__ import annotations

import pytest

from app.runtime import guardrails as g


# --- Language mirroring (rule 4) ---------------------------------------------
def test_detect_language_hebrew():
    assert g.detect_language("יש לכם ספה לבנה?") == "he"


def test_detect_language_english():
    assert g.detect_language("Do you have a white sofa?") == "en"


def test_detect_language_empty_defaults_english():
    assert g.detect_language("") == "en"


def test_detect_language_mixed_is_hebrew_if_any_hebrew():
    assert g.detect_language("Sofa? יש?") == "he"


# --- Price honesty (rules 2 & 3) ---------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "The white sofa is ₪4,990.",
        "It costs 4990 ILS.",
        "Price: 4,990 shekels.",
        "המחיר הוא ₪4990",
        'המחיר 4,990 ש"ח',
    ],
)
def test_supported_price_passes(reply):
    assert g.unsupported_price_claim(reply, [4990.0]) is None


def test_unsupported_price_is_flagged():
    assert g.unsupported_price_claim("It's ₪5,000.", [4990.0]) == 5000.0


def test_bare_number_is_not_flagged():
    # No currency marker → never a price claim.
    assert g.unsupported_price_claim("We have 3 white sofas in stock.", []) is None


def test_time_like_number_not_flagged():
    assert g.unsupported_price_claim("We're open until 18:00 today.", []) is None


def test_first_unsupported_amount_returned():
    reply = "The sofa is ₪4,990 and the lamp is ₪999."
    assert g.unsupported_price_claim(reply, [4990.0]) == 999.0


def test_extract_currency_amounts_variants():
    amounts = g.extract_currency_amounts("₪1,200 or 1200 ILS or 1200 shekels")
    assert amounts == [1200.0, 1200.0, 1200.0]


# --- Handoff triggers (rule 5) -----------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "Can I speak to a human?",
        "I want to talk to a person",
        "connect me with a representative",
        "אני רוצה לדבר עם נציג",
        "תחבר אותי לבן אדם",
    ],
)
def test_wants_human(text):
    assert g.wants_human(text) is True
    assert g.should_handoff(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "This is ridiculous and useless!",
        "worst service ever",
        "השירות הזה גרוע ונמאס לי",
    ],
)
def test_is_angry(text):
    assert g.is_angry(text) is True
    assert g.should_handoff(text) is True


@pytest.mark.parametrize(
    "text",
    ["Do you have a white sofa?", "What are your opening hours?", "יש לכם מנורה?"],
)
def test_benign_text_no_handoff(text):
    assert g.should_handoff(text) is False


# --- Misc --------------------------------------------------------------------
def test_fallback_reply_language():
    assert "human" in g.fallback_reply("en").lower()
    assert g.detect_language(g.fallback_reply("he")) == "he"


def test_system_preamble_includes_language_and_time():
    block = g.system_preamble("he", "Sunday 2026-06-14 10:30")
    assert "Hebrew" in block
    assert "2026-06-14" in block
