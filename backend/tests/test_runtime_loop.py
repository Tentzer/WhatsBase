"""Conversation-loop tests with a mocked Anthropic client (no credentials).

The loop's single model call is `conversation._call_model`; tests replace it
with scripted responses. Fake content blocks duck-type the Anthropic SDK
(`.type`, `.text`, `.name`, `.input`, `.id`).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.retrieval.types import ProductHit
from app.runtime import conversation, guardrails
from app.runtime.context import TurnContext


# --- fakes -------------------------------------------------------------------
class TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class ToolUseBlock:
    def __init__(self, tool_id: str, name: str, tool_input: dict):
        self.type = "tool_use"
        self.id = tool_id
        self.name = name
        self.input = tool_input


class FakeResp:
    def __init__(self, content: list, stop_reason: str = "end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class FakeEnqueue:
    def __init__(self):
        self.jobs: list[dict] = []

    async def __call__(self, payload: dict) -> None:
        self.jobs.append(payload)


def _script(responses):
    """Return an async _call_model that yields the given responses in order and
    records the messages passed to each call."""
    seen: list[list[dict]] = []
    queue = list(responses)

    async def _call(model_cfg, system, messages):
        seen.append([dict(role=m["role"], content=m["content"]) for m in messages])
        return queue.pop(0)

    _call.seen = seen  # type: ignore[attr-defined]
    return _call


@pytest.fixture(autouse=True)
def _no_langfuse(monkeypatch):
    monkeypatch.setattr(conversation, "update_trace", lambda **k: None)
    monkeypatch.setattr(conversation, "get_current_trace_id", lambda: "trace-test")


def _hit(pid="p1", **kw):
    base = dict(
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
    base.update(kw)
    return ProductHit(**base)


# --- tests -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_max_iteration_fallback(monkeypatch):
    """Model never stops calling tools → graceful fallback after 6 iterations."""
    call = _script([FakeResp([ToolUseBlock(f"t{i}", "get_business_info", {})]) for i in range(8)])
    monkeypatch.setattr(conversation, "_call_model", call)

    async def fake_dispatch(name, tool_input, ctx):
        return "info"

    monkeypatch.setattr(conversation.runtime_tools, "dispatch", fake_dispatch)

    ctx = TurnContext(tenant_id="t1")
    res = await conversation.run_turn(
        tenant_id="t1", system_prompt="sp", history=[], user_text="hello", ctx=ctx
    )
    assert len(call.seen) == conversation.MAX_ITERATIONS
    assert res.reply_text == guardrails.fallback_reply("en")


@pytest.mark.asyncio
async def test_tool_result_flows_back(monkeypatch):
    """A tool_use turn is followed by a tool_result user message on the next call."""
    call = _script(
        [
            FakeResp([ToolUseBlock("t1", "search_products", {"query": "sofa"})]),
            FakeResp([TextBlock("Here is what I found.")]),
        ]
    )
    monkeypatch.setattr(conversation, "_call_model", call)

    async def fake_dispatch(name, tool_input, ctx):
        return "Matching products: id=p1 ..."

    monkeypatch.setattr(conversation.runtime_tools, "dispatch", fake_dispatch)

    ctx = TurnContext(tenant_id="t1")
    res = await conversation.run_turn(
        tenant_id="t1", system_prompt="sp", history=[], user_text="got sofas?", ctx=ctx
    )
    assert res.reply_text == "Here is what I found."
    # Second model call saw: user(text), assistant(tool_use), user(tool_result)
    second = call.seen[1]
    assert second[-1]["role"] == "user"
    assert isinstance(second[-1]["content"], list)
    assert second[-1]["content"][0]["type"] == "tool_result"


@pytest.mark.asyncio
async def test_send_product_cards_enqueues_image_jobs(monkeypatch):
    """Through the real tool, send_product_cards enqueues one image job per card
    and never calls the adapter."""
    call = _script(
        [
            FakeResp([ToolUseBlock("t1", "send_product_cards", {"product_ids": ["p1"]})]),
            FakeResp([TextBlock("Sent it.")]),
        ]
    )
    monkeypatch.setattr(conversation, "_call_model", call)

    enqueue = FakeEnqueue()
    ctx = TurnContext(
        tenant_id="t1",
        conversation_id="c1",
        channel="whatsapp",
        green_api_instance_id="inst-1",
        chat_id="972500000000@c.us",
        enqueue_outgoing=enqueue,
    )
    ctx.hits_by_id["p1"] = _hit("p1")  # cached from a prior search → no DB hit

    res = await conversation.run_turn(
        tenant_id="t1", system_prompt="sp", history=[], user_text="show me", ctx=ctx
    )

    assert res.reply_text == "Sent it."
    assert len(res.cards) == 1 and res.cards[0].id == "p1"
    assert len(enqueue.jobs) == 1
    job = enqueue.jobs[0]
    assert job["type"] == "image"
    assert job["image_url"] == "https://img/sofa.jpg"
    assert job["chat_id"] == "972500000000@c.us"
    assert "White Sofa" in job["caption"]


@pytest.mark.asyncio
async def test_hebrew_fallback_language(monkeypatch):
    """Empty model reply to a Hebrew message → Hebrew fallback."""
    call = _script([FakeResp([TextBlock("")])])
    monkeypatch.setattr(conversation, "_call_model", call)
    ctx = TurnContext(tenant_id="t1")
    res = await conversation.run_turn(
        tenant_id="t1", system_prompt="sp", history=[], user_text="יש לכם ספה?", ctx=ctx
    )
    assert guardrails.detect_language(res.reply_text) == "he"


@pytest.mark.asyncio
async def test_unsupported_price_blocked(monkeypatch):
    """A price not backed by any tool result is replaced with a fallback."""
    call = _script([FakeResp([TextBlock("It costs ₪9,999.")])])
    monkeypatch.setattr(conversation, "_call_model", call)
    ctx = TurnContext(tenant_id="t1")
    res = await conversation.run_turn(
        tenant_id="t1", system_prompt="sp", history=[], user_text="price?", ctx=ctx
    )
    assert "9,999" not in res.reply_text
    assert res.reply_text == guardrails.fallback_reply("en")


@pytest.mark.asyncio
async def test_supported_price_passes(monkeypatch):
    """A price that matches a tool-result price is allowed through."""
    call = _script([FakeResp([TextBlock("The white sofa is ₪4,990.")])])
    monkeypatch.setattr(conversation, "_call_model", call)
    ctx = TurnContext(tenant_id="t1")
    ctx.tool_prices.add(4990.0)
    res = await conversation.run_turn(
        tenant_id="t1", system_prompt="sp", history=[], user_text="how much?", ctx=ctx
    )
    assert res.reply_text == "The white sofa is ₪4,990."
