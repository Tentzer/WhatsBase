from __future__ import annotations

from pathlib import Path

from app.builder.business_info_loader import merge_business_info_items, parse_business_info_txt
from app.builder.context import BusinessInfoItem
from app.builder.onboarding_assets import write_business_info_txt
from app.core.schema import BusinessInfo


def test_parse_business_info_txt_roundtrip(tmp_path: Path):
    rows = [
        BusinessInfo(
            tenant_id="tenant-1",
            topic="hours",
            content_he="ראשון-חמישי 9-17",
            content_en="Sun-Thu 9-17",
        ),
        BusinessInfo(
            tenant_id="tenant-1",
            topic="policy",
            content_he="משלוח 7 ימים",
            content_en="Delivery 7 days",
        ),
    ]
    dest = tmp_path / "business_info.txt"
    write_business_info_txt(rows, dest)

    parsed = parse_business_info_txt(dest)
    assert len(parsed) == 2
    assert parsed[0].topic == "hours"
    assert parsed[0].content_he == "ראשון-חמישי 9-17"
    assert parsed[1].topic == "policy"


def test_merge_business_info_items_dedupes():
    existing = [
        BusinessInfoItem(topic="hours", content_he="א", content_en="A"),
    ]
    incoming = [
        BusinessInfoItem(topic="hours", content_he="א", content_en="A"),
        BusinessInfoItem(topic="faq", content_he="ש", content_en="Q"),
    ]
    merged = merge_business_info_items(existing, incoming)
    assert len(merged) == 2
    assert merged[1].topic == "faq"
