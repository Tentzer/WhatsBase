"""Debouncer + WhatsApp intake wiring tests (FakeRedis, mocked turn)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.intake import tasks
from app.runtime.types import ProductCard, TurnResult


class FakeRedis:
    def __init__(self):
        self.kv: dict = {}
        self.lists: dict[str, list] = {}
        self.jobs: list[tuple] = []

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    async def get(self, key):
        return self.kv.get(key)

    async def incr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) + 1
        return self.kv[key]

    async def expire(self, key, ttl):
        return True

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    async def lrange(self, key, start, end):
        return list(self.lists.get(key, []))

    async def delete(self, key):
        self.lists.pop(key, None)
        self.kv.pop(key, None)
        return 1

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))


def _payload(message_id="m1", text="hi", chat_id="972500000000@c.us"):
    return {
        "instance_id": "inst-1",
        "message_id": message_id,
        "chat_id": chat_id,
        "sender": chat_id,
        "type": "text",
        "text": text,
        "media_url": None,
        "caption": None,
    }


@pytest.fixture(autouse=True)
def _empty_allowlist(monkeypatch):
    monkeypatch.setattr(
        tasks, "get_settings", lambda: SimpleNamespace(allowed_test_numbers="")
    )


# --- process_incoming_message: buffer + debounce -----------------------------
@pytest.mark.asyncio
async def test_buffers_and_schedules_turn():
    redis = FakeRedis()
    await tasks.process_incoming_message({"redis": redis}, _payload())

    burst = redis.lists[tasks._burst_key("inst-1", "972500000000@c.us")]
    assert len(burst) == 1
    turn_jobs = [j for j in redis.jobs if j[0] == "run_agent_turn"]
    assert len(turn_jobs) == 1
    name, args, kwargs = turn_jobs[0]
    assert args == ("inst-1", "972500000000@c.us", 1)
    assert kwargs["_defer_by"] == tasks._DEBOUNCE_SECONDS


@pytest.mark.asyncio
async def test_idempotent_duplicate_skipped():
    redis = FakeRedis()
    await tasks.process_incoming_message({"redis": redis}, _payload("m1"))
    await tasks.process_incoming_message({"redis": redis}, _payload("m1"))  # dup
    burst = redis.lists[tasks._burst_key("inst-1", "972500000000@c.us")]
    assert len(burst) == 1  # second was skipped


@pytest.mark.asyncio
async def test_burst_merges_and_token_advances():
    redis = FakeRedis()
    await tasks.process_incoming_message({"redis": redis}, _payload("m1", "white"))
    await tasks.process_incoming_message({"redis": redis}, _payload("m2", "sofa?"))
    burst = redis.lists[tasks._burst_key("inst-1", "972500000000@c.us")]
    assert len(burst) == 2
    tokens = [j[1][2] for j in redis.jobs if j[0] == "run_agent_turn"]
    assert tokens == [1, 2]


@pytest.mark.asyncio
async def test_group_chat_dropped(monkeypatch):
    monkeypatch.setattr(
        tasks, "get_settings", lambda: SimpleNamespace(allowed_test_numbers="972500000000")
    )
    redis = FakeRedis()
    await tasks.process_incoming_message(
        {"redis": redis}, _payload(chat_id="123@g.us")
    )
    assert "run_agent_turn" not in [j[0] for j in redis.jobs]


# --- run_agent_turn: token guard ---------------------------------------------
@pytest.mark.asyncio
async def test_superseded_token_is_noop():
    redis = FakeRedis()
    redis.kv[tasks._token_key("inst-1", "c@c.us")] = 5  # current token is 5
    burst_key = tasks._burst_key("inst-1", "c@c.us")
    redis.lists[burst_key] = [json.dumps(_payload())]
    await tasks.run_agent_turn({"redis": redis}, "inst-1", "c@c.us", token=3)
    # burst untouched, no jobs enqueued
    assert burst_key in redis.lists
    assert redis.jobs == []


# --- run_agent_turn: happy path (mocked DB + run_turn) -----------------------
class FakeResult:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        # Used by queries that return multiple rows (e.g. validate_tenant_products).
        # Return empty list — no products/rows exist in the fake session.
        return []


class FakeSession:
    def __init__(self, instance):
        self._instance = instance
        self.added: list = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, *a, **k):
        # Dispatch by which table the statement targets so the two-query flow
        # in run_agent_turn is modelled correctly:
        #   1. select(WhatsAppInstance) → return the fake instance
        #   2. select(Lead)             → return None (no pre-existing lead)
        if "whatsapp_instances" in str(stmt):
            return FakeResult(self._instance)
        return FakeResult(None)

    async def get(self, model_class, pk):
        # Called by _upsert_lead_after_turn to fetch the Tenant for business_name.
        return SimpleNamespace(name="Test Business")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass


@pytest.mark.asyncio
async def test_run_agent_turn_persists_and_sends(monkeypatch):
    redis = FakeRedis()
    chat = "972500000000@c.us"
    redis.kv[tasks._token_key("inst-1", chat)] = 1
    redis.lists[tasks._burst_key("inst-1", chat)] = [
        json.dumps(_payload("m1", "white sofa?", chat))
    ]

    instance = SimpleNamespace(tenant_id="t1")
    session = FakeSession(instance)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    async def fake_load_agent(session, tenant_id):
        return SimpleNamespace(status="live", system_prompt="sp")

    async def fake_conv(session, tenant_id, phone):
        return SimpleNamespace(id="c1", last_message_at=None)

    async def fake_recent(session, conv_id, limit=12):
        return []

    monkeypatch.setattr(tasks.memory, "load_agent", fake_load_agent)
    monkeypatch.setattr(tasks.memory, "get_or_create_conversation", fake_conv)
    monkeypatch.setattr(tasks.memory, "recent_messages", fake_recent)

    captured = {}

    async def fake_run_turn(**kwargs):
        captured.update(kwargs)
        return TurnResult(
            reply_text="הנה הספה",
            cards=[
                ProductCard(
                    id="p1",
                    image_url="https://img/sofa.jpg",
                    name_he="ספה לבנה",
                    name_en="White Sofa",
                    price=4990.0,
                    currency="ILS",
                )
            ],
            handoff=False,
            trace_id="trace-1",
        )

    monkeypatch.setattr(tasks, "run_turn", fake_run_turn)

    await tasks.run_agent_turn({"redis": redis}, "inst-1", chat, token=1)

    # run_turn received the merged text + whatsapp context
    assert captured["user_text"] == "white sofa?"
    assert captured["ctx"].channel == "whatsapp"
    assert captured["ctx"].enqueue_outgoing is not None

    # Final text reply was enqueued for sending
    text_jobs = [
        j for j in redis.jobs if j[0] == "send_outgoing" and j[1][0].get("type") == "text"
    ]
    assert text_jobs and text_jobs[0][1][0]["text"] == "הנה הספה"

    # Persisted: 1 inbound text + 1 outbound image card + 1 outbound text,
    # the outbound rows tagged with the trace id (the amendment: cards persisted too).
    # Filter to Message rows only — session.added also contains the new Lead row
    # created by _upsert_lead_after_turn when no pre-existing lead is found.
    messages = [m for m in session.added if hasattr(m, "direction")]
    persisted = [(m.direction, m.type) for m in messages]
    assert persisted == [
        ("inbound", "text"),
        ("outbound", "image"),
        ("outbound", "text"),
    ]
    outbound = [m for m in messages if m.direction == "outbound"]
    assert all(m.agent_trace_id == "trace-1" for m in outbound)
    image_row = next(m for m in outbound if m.type == "image")
    assert image_row.media_url == "https://img/sofa.jpg"


@pytest.mark.asyncio
async def test_run_agent_turn_skips_when_auto_reply_disabled(monkeypatch):
    redis = FakeRedis()
    chat = "972500000000@c.us"
    redis.kv[tasks._token_key("inst-1", chat)] = 1
    redis.lists[tasks._burst_key("inst-1", chat)] = [
        json.dumps(_payload("m1", "hi", chat))
    ]

    instance = SimpleNamespace(tenant_id="t1")
    session = FakeSession(instance)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    async def fake_load_agent(session, tenant_id):  # noqa: ARG001
        return SimpleNamespace(
            status="live",
            system_prompt="sp",
            auto_reply_enabled=False,
        )

    monkeypatch.setattr(tasks.memory, "load_agent", fake_load_agent)

    await tasks.run_agent_turn({"redis": redis}, "inst-1", chat, token=1)

    assert not redis.jobs
    assert not session.added
