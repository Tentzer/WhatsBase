from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.intake import tasks


class _FakeRedis:
    def __init__(self, set_returns: bool | None = True):
        self.jobs: list[tuple[str, tuple, dict]] = []
        self._set_returns = set_returns

    async def set(self, key, value, nx=False, ex=None):  # noqa: ANN001, ARG002
        return self._set_returns

    async def enqueue_job(self, name, *args, **kwargs):  # noqa: ANN001
        self.jobs.append((name, args, kwargs))


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeScalarsResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.added: list = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):  # noqa: ANN002, ARG002
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_scan_reengagement_candidates_caps_per_tenant(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(
            reengagement_enabled=True,
            reengagement_stale_days=60,
            reengagement_max_daily_per_tenant=1,
            reengagement_max_attempts_per_lead=3,
        ),
    )
    session = _FakeSession(
        [
            _FakeRowsResult(
                [
                    ("lead-a", "tenant-1"),
                    ("lead-b", "tenant-1"),
                    ("lead-c", "tenant-2"),
                ]
            )
        ]
    )
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    redis = _FakeRedis()

    await tasks.scan_reengagement_candidates({"redis": redis})

    queued = [job for job in redis.jobs if job[0] == "evaluate_reengagement_candidate"]
    assert len(queued) == 2
    assert queued[0][1][0] == "tenant-1"
    assert queued[1][1][0] == "tenant-2"


@pytest.mark.asyncio
async def test_evaluate_reengagement_candidate_duplicate_skips(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(reengagement_enabled=True),
    )

    redis = _FakeRedis(set_returns=None)

    class _ExplodingSession:
        async def __aenter__(self):
            raise AssertionError("should not open DB session for duplicate key")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(tasks, "SessionLocal", lambda: _ExplodingSession())

    await tasks.evaluate_reengagement_candidate({"redis": redis}, "tenant-1", "lead-1")


@pytest.mark.asyncio
async def test_evaluate_reengagement_candidate_low_confidence_no_send(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(
            reengagement_enabled=True,
            reengagement_max_attempts_per_lead=3,
            reengagement_stale_days=60,
            reengagement_min_confidence=0.8,
            reengagement_dry_run=False,
            reengagement_cooldown_days=30,
            allowed_test_numbers="",
        ),
    )
    lead = SimpleNamespace(
        id="lead-1",
        tenant_id="tenant-1",
        status="not_interested",
        phone_number="972501111111",
        reengagement_attempt_count=0,
        reengagement_cooldown_until=None,
        last_message_sent_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        conversation_id=None,
        last_conversation_summary="customer asked to revisit later",
        last_reengagement_decision=None,
    )
    session = _FakeSession(
        [
            _FakeScalarResult(lead),
            _FakeScalarResult(SimpleNamespace(id="agent-1", status="live")),
            _FakeScalarsResult(SimpleNamespace(green_api_instance_id="inst-1")),
        ]
    )
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(tasks.memory, "recent_messages", lambda *a, **k: [])  # noqa: ARG005
    async def _fake_judge(**kwargs):  # noqa: ARG001
        return SimpleNamespace(
            decision="message_again",
            confidence=0.2,
            reason_code="temporary_constraint",
            recommended_message="Hello again",
        )

    monkeypatch.setattr(tasks, "judge_reengagement_candidate", _fake_judge)
    redis = _FakeRedis(set_returns=True)

    await tasks.evaluate_reengagement_candidate({"redis": redis}, "tenant-1", "lead-1")

    assert lead.last_reengagement_decision == "do_not_message"
    assert not [job for job in redis.jobs if job[0] == "send_outgoing"]
    assert session.commits == 1
