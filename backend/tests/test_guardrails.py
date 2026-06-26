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


# --- Lead-qualification: any_price_mention -----------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "The program costs ₪500 per month.",
        "It's 1,200 ILS for the full package.",
        "Only 300 shekels!",
        "המחיר הוא ₪800",
    ],
)
def test_any_price_mention_detects_currency(text):
    assert g.any_price_mention(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Tell me more about what you're looking for.",
        "We'd love to connect you with the team.",
        "What brings you here today?",
        "Open until 18:00, we have 3 locations.",
    ],
)
def test_any_price_mention_no_currency(text):
    assert g.any_price_mention(text) is False


# --- system_preamble agent_type branching ------------------------------------
def test_system_preamble_catalog_sales_contains_catalog_rules():
    """Default (catalog_sales) preamble includes the catalog-specific guardrail block."""
    block = g.system_preamble("en", "Monday 2026-06-24 08:00")
    # Catalog guardrail has price-from-tool rule
    assert "search_products" in block
    # Should NOT include lead-qual no-price rule
    assert "NEVER discuss" not in block


def test_system_preamble_leadqual_contains_no_price_rule():
    """lead_qualification preamble uses RUNTIME_GUARDRAILS_LEADQUAL."""
    block = g.system_preamble("en", "Monday 2026-06-24 08:00", agent_type="lead_qualification")
    assert "NEVER discuss" in block
    assert "prices" in block.lower()
    # Must not include catalog-only rules
    assert "search_products" not in block


def test_system_preamble_leadqual_hebrew_includes_hebrew_directive():
    block = g.system_preamble("he", "Monday 2026-06-24 08:00", agent_type="lead_qualification")
    assert "Hebrew" in block
    assert "NEVER discuss" in block


def test_leadqual_guardrails_block_is_exported():
    """RUNTIME_GUARDRAILS_LEADQUAL is importable for use in tests / monitoring."""
    assert "prices" in g.RUNTIME_GUARDRAILS_LEADQUAL.lower()
    assert "handoff_to_human" in g.RUNTIME_GUARDRAILS_LEADQUAL


def test_leadqual_guardrails_contains_medical_directive():
    """RUNTIME_GUARDRAILS_LEADQUAL must include the medical-handoff directive.

    Dual-enforcement (Invariant #8): the same rule appears in
    LEAD_QUALIFICATION_TEMPLATE rule 5 AND in this runtime block so it is
    enforced on every turn regardless of whether the generated prompt is loaded.
    """
    block = g.RUNTIME_GUARDRAILS_LEADQUAL
    assert "medical" in block.lower(), (
        "RUNTIME_GUARDRAILS_LEADQUAL must contain a medical-safety / medical-handoff directive"
    )


# --- Emoji stripping (lead_qualification mechanical backstop) ----------------
def test_strip_emojis_removes_emoji():
    """Emoji characters are stripped; non-emoji text is preserved."""
    result = g.strip_emojis("שלום 👋 מה נשמע 😊")
    assert "👋" not in result
    assert "😊" not in result
    assert "שלום" in result
    assert "מה נשמע" in result


def test_strip_emojis_plain_text_unchanged():
    """Text with no emoji passes through strip_emojis unchanged."""
    text = "No emojis here, just plain text."
    assert g.strip_emojis(text) == text


def test_system_preamble_leadqual_has_no_emoji_directive():
    """Lead-qual preamble contains an explicit no-emoji override injected after RUNTIME_VOICE."""
    block = g.system_preamble("en", "Monday 2026-06-24 08:00", agent_type="lead_qualification")
    assert "No emojis" in block


def test_system_preamble_catalog_sales_no_emoji_ban():
    """Catalog-sales preamble does NOT include the lead-qual emoji ban."""
    block = g.system_preamble("en", "Monday 2026-06-24 08:00", agent_type="catalog_sales")
    assert "No emojis" not in block
