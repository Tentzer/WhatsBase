from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.leads import service


def test_normalize_phone():
    assert service.normalize_phone("054-123-4567") == "972541234567"
    assert service.normalize_phone("+972541234567") == "972541234567"
    assert service.normalize_phone("abc") == "abc"


@pytest.mark.asyncio
async def test_generate_lead_summary_from_llm(monkeypatch):
    class _Messages:
        def create(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=(
                            "customer intent: wants a sofa\n"
                            "interested products (from sent cards / mentioned products): White Sofa\n"
                            "objections (price, delivery, etc.): price\n"
                            "current stage (pending/qualified/not_interested/success): qualified\n"
                            "next suggested follow-up: send discounted quote"
                        ),
                    )
                ]
            )

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(service, "_get_anthropic_client", lambda: _Client())
    out = await service.generate_lead_summary(
        messages=[SimpleNamespace(direction="inbound", content="I want a white sofa")],
        stage="qualified",
        interested_product_hints=["White Sofa"],
    )
    assert "customer intent:" in out
    assert "current stage (pending/qualified/not_interested/success): qualified" in out


@pytest.mark.asyncio
async def test_generate_lead_summary_fallback_on_failure(monkeypatch):
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_get_anthropic_client", _raise)
    out = await service.generate_lead_summary(
        messages=[SimpleNamespace(direction="inbound", content="How much is shipping?")],
        stage="pending",
        interested_product_hints=[],
    )
    assert "customer intent:" in out
    assert "interested products (from sent cards / mentioned products):" in out
    assert "objections (price, delivery, etc.):" in out
    assert "current stage (pending/qualified/not_interested/success): pending" in out
    assert "next suggested follow-up:" in out


@pytest.mark.asyncio
async def test_judge_reengagement_candidate_parses_json(monkeypatch):
    class _Messages:
        def create(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=(
                            '{"decision":"message_again","confidence":0.86,'
                            '"reason_code":"temporary_constraint",'
                            '"recommended_message":"Hi! Just checking if now is a better time."}'
                        ),
                    )
                ]
            )

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(service, "_get_anthropic_client", lambda: _Client())
    out = await service.judge_reengagement_candidate(
        lead_summary="customer intent: maybe later",
        messages=[SimpleNamespace(direction="inbound", content="Not now, message me next month")],
        status="not_interested",
        attempts=1,
        days_since_last_contact=62,
    )
    assert out.decision == "message_again"
    assert out.reason_code == "temporary_constraint"


@pytest.mark.asyncio
async def test_judge_reengagement_candidate_hard_opt_out_short_circuit(monkeypatch):
    called = {"value": False}

    def _unexpected_call():
        called["value"] = True
        raise AssertionError("LLM should not be called for hard opt-out")

    monkeypatch.setattr(service, "_get_anthropic_client", _unexpected_call)
    out = await service.judge_reengagement_candidate(
        lead_summary="Customer wrote: please do not contact me again.",
        messages=[],
        status="not_interested",
        attempts=0,
        days_since_last_contact=60,
    )
    assert out.decision == "do_not_message"
    assert out.reason_code == "hard_opt_out"
    assert called["value"] is False

# ── get_messages_for_lead ──────────────────────────────────────────────────────

class _FakeResult:
    """Fake execute() result that supports all call styles used by the service."""

    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows if rows is not None else []

    def one_or_none(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, *args, **kwargs):  # noqa: ANN002, ARG002
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_get_messages_for_lead_returns_messages():
    """Happy path: lead with conversation returns messages in order."""
    lead_row = SimpleNamespace(id="lead-1", conversation_id="conv-1")
    msg1 = SimpleNamespace(
        id="msg-1", direction="inbound", type="text", content="Hello",
        media_url=None, created_at=None,
    )
    msg2 = SimpleNamespace(
        id="msg-2", direction="outbound", type="text", content="Hi!",
        media_url=None, created_at=None,
    )
    session = _FakeSession([
        _FakeResult(value=lead_row),          # lead lookup
        _FakeResult(value="conv-1"),          # conversation tenant check
        _FakeResult(rows=[msg1, msg2]),       # messages query
    ])
    msgs = await service.get_messages_for_lead(
        session, lead_id="lead-1", tenant_id="tenant-A"
    )
    assert [m.id for m in msgs] == ["msg-1", "msg-2"]


@pytest.mark.asyncio
async def test_get_messages_for_lead_tenant_isolation():
    """Tenant isolation wall: conversation owned by a different tenant returns []."""
    lead_row = SimpleNamespace(id="lead-1", conversation_id="conv-other-tenant")
    session = _FakeSession([
        _FakeResult(value=lead_row),   # lead lookup succeeds (lead row exists)
        _FakeResult(value=None),       # conversation tenant check fails
    ])
    msgs = await service.get_messages_for_lead(
        session, lead_id="lead-1", tenant_id="tenant-A"
    )
    assert msgs == []


@pytest.mark.asyncio
async def test_get_messages_for_lead_null_conversation_id():
    """Lead with no WhatsApp conversation yet returns [] without further DB calls."""
    lead_row = SimpleNamespace(id="lead-1", conversation_id=None)
    session = _FakeSession([_FakeResult(value=lead_row)])
    msgs = await service.get_messages_for_lead(
        session, lead_id="lead-1", tenant_id="tenant-A"
    )
    assert msgs == []

