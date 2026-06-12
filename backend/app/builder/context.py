from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.builder.report import BuildReport


@dataclass
class BusinessInfoItem:
    topic: str
    content_he: str
    content_en: str


@dataclass
class BuildContext:
    tenant_id: str
    assets_dir: Path
    dry_run: bool
    session: AsyncSession
    build_run_id: str | None = None
    catalog_source: str = "assets"  # assets | api
    report: BuildReport = field(default_factory=BuildReport)
    self_test_passed: bool = False
    # Business info accumulates here; written to DB during index_embeddings.
    business_info_items: list[BusinessInfoItem] = field(default_factory=list)
    # Loaded assets keyed by stable_key; populated during list_uploaded_assets.
    # Used by create_or_update_product for assumption detection.
    assets: dict = field(default_factory=dict)
