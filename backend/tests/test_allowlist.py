"""Test-mode allowlist filter — covers four cases:
- allowed direct chat → processed
- non-allowed direct chat → dropped
- group chat → dropped (when allowlist active)
- empty allowlist → everything processed
"""

from __future__ import annotations

import pytest

from app.intake.tasks import _is_allowed, _parse_allowlist, process_incoming_message


class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self.enqueued: list[tuple[str, dict]] = []

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True

    async def enqueue_job(self, name, payload):
        self.enqueued.append((name, payload))


def _payload(chat_id: str, message_id: str = "MSG_A") -> dict:
    return {
        "instance_id": "111",
        "message_id": message_id,
        "chat_id": chat_id,
        "sender": chat_id,
        "type": "text",
        "text": "hello",
    }


# ---------- pure-function tests ----------


def test_parse_allowlist_handles_whitespace_and_blanks():
    assert _parse_allowlist("") == set()
    assert _parse_allowlist("  ") == set()
    assert _parse_allowlist("972545495209") == {"972545495209"}
    assert _parse_allowlist("972545495209, 972500000000 ,") == {
        "972545495209",
        "972500000000",
    }


def test_is_allowed_empty_allowlist_lets_everything_through():
    al = set()
    assert _is_allowed("972545495209@c.us", al) is True
    assert _is_allowed("120363402096476116@g.us", al) is True


def test_is_allowed_filters_direct_chats():
    al = {"972545495209"}
    assert _is_allowed("972545495209@c.us", al) is True
    assert _is_allowed("972500000000@c.us", al) is False


def test_is_allowed_drops_groups_when_allowlist_active():
    al = {"972545495209"}
    assert _is_allowed("120363402096476116@g.us", al) is False


# ---------- end-to-end through process_incoming_message ----------


@pytest.mark.asyncio
async def test_allowed_sender_is_enqueued(monkeypatch):
    monkeypatch.setenv("ALLOWED_TEST_NUMBERS", "972545495209")
    from app.core.config import get_settings
    get_settings.cache_clear()

    redis = FakeRedis()
    await process_incoming_message({"redis": redis}, _payload("972545495209@c.us"))

    assert len(redis.enqueued) == 1
    assert redis.enqueued[0][0] == "send_outgoing"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_non_allowed_sender_is_dropped(monkeypatch):
    monkeypatch.setenv("ALLOWED_TEST_NUMBERS", "972545495209")
    from app.core.config import get_settings
    get_settings.cache_clear()

    redis = FakeRedis()
    await process_incoming_message({"redis": redis}, _payload("972500000000@c.us"))

    assert redis.enqueued == []

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_group_chat_dropped_when_allowlist_active(monkeypatch):
    monkeypatch.setenv("ALLOWED_TEST_NUMBERS", "972545495209")
    from app.core.config import get_settings
    get_settings.cache_clear()

    redis = FakeRedis()
    await process_incoming_message(
        {"redis": redis}, _payload("120363402096476116@g.us")
    )

    assert redis.enqueued == []

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_empty_allowlist_lets_everything_through(monkeypatch):
    monkeypatch.setenv("ALLOWED_TEST_NUMBERS", "")
    from app.core.config import get_settings
    get_settings.cache_clear()

    redis = FakeRedis()
    await process_incoming_message({"redis": redis}, _payload("972500000000@c.us"))
    await process_incoming_message(
        {"redis": redis}, _payload("120363402096476116@g.us", message_id="MSG_B")
    )

    assert len(redis.enqueued) == 2

    get_settings.cache_clear()
