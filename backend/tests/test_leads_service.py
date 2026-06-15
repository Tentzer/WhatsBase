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

