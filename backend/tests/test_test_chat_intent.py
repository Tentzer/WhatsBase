"""Test-chat intent: casual greetings should not trigger catalog retrieval."""

from app.api.agent_runtime import _is_casual_greeting


def test_casual_greetings_skip_catalog():
    assert _is_casual_greeting("מה נשמע")
    assert _is_casual_greeting("שלום!")
    assert _is_casual_greeting("hi")
    assert _is_casual_greeting("How are you?")
    assert _is_casual_greeting("thanks")


def test_product_questions_search_catalog():
    assert not _is_casual_greeting("יש לכם ספה לבנה?")
    assert not _is_casual_greeting("Do you have a white sofa?")
    assert not _is_casual_greeting("מה המחיר של המיטה?")
    assert not _is_casual_greeting("What are your hours?")
