"""Business info helpers — one row per topic per tenant."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from app.core.schema import BusinessInfo

T = TypeVar("T")

BUSINESS_INFO_TOPIC_ORDER = ("hours", "location", "policy", "faq", "other")


def dedupe_business_info_payload(items: list[T], *, topic_getter) -> list[T]:
    """Keep the last item per topic in payload order."""
    by_topic: dict[str, T] = {}
    for item in items:
        by_topic[topic_getter(item)] = item
    return [by_topic[topic] for topic in BUSINESS_INFO_TOPIC_ORDER if topic in by_topic]


def dedupe_business_info_rows(rows: list["BusinessInfo"]) -> list["BusinessInfo"]:
    """Keep the newest row per topic (by updated_at, then created_at)."""
    by_topic: dict[str, BusinessInfo] = {}
    for row in rows:
        existing = by_topic.get(row.topic)
        if existing is None:
            by_topic[row.topic] = row
            continue
        row_stamp = (row.updated_at, row.created_at)
        existing_stamp = (existing.updated_at, existing.created_at)
        if row_stamp >= existing_stamp:
            by_topic[row.topic] = row
    return [by_topic[topic] for topic in BUSINESS_INFO_TOPIC_ORDER if topic in by_topic]
