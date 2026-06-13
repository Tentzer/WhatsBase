from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.business_info import dedupe_business_info_payload, dedupe_business_info_rows


@dataclass
class _Payload:
    topic: str
    content_en: str


@dataclass
class _Row:
    id: str
    topic: str
    updated_at: datetime
    created_at: datetime


def test_dedupe_payload_keeps_last_per_topic():
    items = [
        _Payload("hours", "old hours"),
        _Payload("hours", "new hours"),
        _Payload("location", "addr"),
    ]
    deduped = dedupe_business_info_payload(items, topic_getter=lambda item: item.topic)
    assert [item.topic for item in deduped] == ["hours", "location"]
    assert deduped[0].content_en == "new hours"


def test_dedupe_rows_keeps_newest_per_topic():
    older = _Row("1", "hours", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _Row("2", "hours", datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc))
    deduped = dedupe_business_info_rows([older, newer])
    assert len(deduped) == 1
    assert deduped[0].id == "2"
