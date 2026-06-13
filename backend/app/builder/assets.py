"""Asset discovery: scan images dir + parse optional CSV, match by filename stem."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Asset:
    filename: str       # e.g. "sofa-white-3seat.webp"
    stem: str           # e.g. "sofa-white-3seat"
    path: Path
    stable_key: str     # sku / stable_key from CSV if present, else stem
    name_he: str | None = None
    name_en: str | None = None
    price: float | None = None
    currency: str = "ILS"
    category: str | None = None
    in_stock: bool = True
    colors: str | None = None
    materials: str | None = None
    style: str | None = None
    csv_matched: bool = False


def load_assets(assets_dir: Path) -> tuple[list[Asset], list[str]]:
    """Return (assets, warnings).

    Warnings describe: unmatched CSV rows (no image) and orphan images (no CSV).
    """
    images_dir = assets_dir / "images"
    if not images_dir.exists():
        return [], [f"images/ directory not found in {assets_dir}"]

    image_files = sorted(
        f for f in images_dir.iterdir()
        if f.suffix.lower() in {".webp", ".jpg", ".jpeg", ".png"}
    )
    by_stem: dict[str, Path] = {f.stem.lower(): f for f in image_files}

    csv_path = assets_dir / "products.csv"
    csv_rows: dict[str, dict] = {}
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                filename = (row.get("image") or row.get("image_filename") or "").strip()
                stem = Path(filename).stem.lower()
                if stem:
                    csv_rows[stem] = row

    assets: list[Asset] = []
    warnings: list[str] = []

    for stem, path in by_stem.items():
        row = csv_rows.get(stem)
        if row:
            sku = row.get("sku", "").strip()
            stable_key_col = row.get("stable_key", "").strip()
            stable_key = sku or stable_key_col or stem
            price_raw = row.get("price", "").strip()
            price = float(price_raw) if price_raw else None
            in_stock_raw = row.get("in_stock", "true").strip().lower()
            in_stock = in_stock_raw not in {"false", "0", "no"}
            asset = Asset(
                filename=path.name,
                stem=stem,
                path=path,
                stable_key=stable_key,
                name_he=row.get("name_he", "").strip() or None,
                name_en=row.get("name_en", "").strip() or None,
                price=price,
                currency=row.get("currency", "ILS").strip() or "ILS",
                category=row.get("category", "").strip() or None,
                in_stock=in_stock,
                colors=row.get("colors", "").strip() or None,
                materials=row.get("materials", "").strip() or None,
                style=row.get("style", "").strip() or None,
                csv_matched=True,
            )
        else:
            warnings.append(f"Orphan image (no CSV row): {path.name}")
            asset = Asset(filename=path.name, stem=stem, path=path, stable_key=stem)

        assets.append(asset)

    for stem in csv_rows:
        if stem not in by_stem:
            warnings.append(f"Unmatched CSV row (no image): stem={stem!r}")

    return assets, warnings
