"""Idempotency tests — same message_id processed exactly once.

Uses a fake in-memory Redis stub so no Redis server is required.
"""

from __future__ import annotations

import pytest


class FakeRedis:
    """Minimal Redis stub for testing NX-set idempotency."""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._lists: dict[str, list] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self._store:
            return None  # Redis returns nil when NX fails
        self._store[key] = value
        return True

    async def rpush(self, key, value):
        self._lists.setdefault(key, []).append(value)
        return len(self._lists[key])

    async def incr(self, key):
        self._store[key] = int(self._store.get(key, 0)) + 1
        return self._store[key]

    async def expire(self, key, ttl):
        return True

    async def enqueue_job(self, name: str, *args, **kwargs) -> None:
        pass  # no-op


def FakeCtx() -> dict:
    """arq passes ctx as a plain dict — mirror that here."""
    return {"redis": FakeRedis()}


@pytest.mark.asyncio
async def test_first_message_is_processed():
    from app.intake.tasks import process_incoming_message

    ctx = FakeCtx()
    payload = {
        "instance_id": "111",
        "message_id": "MSG001",
        "chat_id": "972501234567@c.us",
        "sender": "972501234567@c.us",
        "type": "text",
        "text": "Hello",
    }

    # First call: should set the key and enqueue a reply.
    await process_incoming_message(ctx, payload)

    key = "msg:111:MSG001"
    assert ctx["redis"]._store.get(key) == "1"


@pytest.mark.asyncio
async def test_duplicate_message_is_skipped():
    from app.intake.tasks import process_incoming_message

    ctx = FakeCtx()
    payload = {
        "instance_id": "111",
        "message_id": "MSG002",
        "chat_id": "972501234567@c.us",
        "sender": "972501234567@c.us",
        "type": "text",
        "text": "Hello again",
    }

    # Pre-populate the idempotency key (simulates already-processed).
    ctx["redis"]._store["msg:111:MSG002"] = "1"

    # This call should be a no-op (logged and returned early).
    await process_incoming_message(ctx, payload)

    # Key should still be "1" — not re-set or modified.
    assert ctx["redis"]._store.get("msg:111:MSG002") == "1"
