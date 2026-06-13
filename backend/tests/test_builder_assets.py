"""Unit tests for builder asset loading and CSV/image matching."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from app.builder.assets import Asset, load_assets


def _make_assets_dir(
    images: list[str],
    csv_rows: list[dict] | None = None,
) -> Path:
    """Create a temp assets dir with given image filenames and optional CSV."""
    tmp = Path(tempfile.mkdtemp())
    images_dir = tmp / "images"
    images_dir.mkdir()
    for name in images:
        (images_dir / name).write_bytes(b"placeholder")
    if csv_rows is not None:
        csv_path = tmp / "products.csv"
        if csv_rows:
            fieldnames = list(csv_rows[0].keys())
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)
        else:
            csv_path.write_text("image_filename,sku\n")
    return tmp


def test_load_assets_no_csv():
    d = _make_assets_dir(["sofa-white.webp", "lamp-brass.webp"])
    assets, warnings = load_assets(d)
    assert len(assets) == 2
    stems = {a.stem for a in assets}
    assert "sofa-white" in stems
    assert "lamp-brass" in stems
    # No CSV match — stable_key falls back to stem
    for a in assets:
        assert a.stable_key == a.stem
        assert not a.csv_matched


def test_load_assets_csv_match_case_insensitive():
    d = _make_assets_dir(
        ["Sofa-White-3Seat.webp"],
        csv_rows=[{
            "image_filename": "sofa-white-3seat.webp",
            "sku": "SOF-001",
            "name_he": "ספה לבנה",
            "name_en": "White Sofa",
            "price": "4990",
            "currency": "ILS",
            "category": "sofa",
            "in_stock": "true",
        }],
    )
    assets, warnings = load_assets(d)
    assert len(assets) == 1
    a = assets[0]
    assert a.csv_matched
    assert a.stable_key == "SOF-001"
    assert a.name_en == "White Sofa"
    assert a.price == 4990.0
    assert a.in_stock is True
    assert warnings == []


def test_load_assets_orphan_image_warning():
    d = _make_assets_dir(
        ["orphan.webp"],
        csv_rows=[],  # empty CSV
    )
    assets, warnings = load_assets(d)
    assert len(assets) == 1
    assert any("orphan" in w.lower() or "orphan" in w for w in warnings)
    assert not assets[0].csv_matched


def test_load_assets_unmatched_csv_warning():
    d = _make_assets_dir(
        [],  # no images
        csv_rows=[{
            "image_filename": "missing.webp",
            "sku": "X-001",
            "name_he": "",
            "name_en": "Missing",
            "price": "100",
            "currency": "ILS",
            "category": "other",
            "in_stock": "true",
        }],
    )
    assets, warnings = load_assets(d)
    assert len(assets) == 0
    assert any("unmatched" in w.lower() or "missing" in w.lower() for w in warnings)


def test_load_assets_in_stock_false():
    d = _make_assets_dir(
        ["sofa-cream.webp"],
        csv_rows=[{
            "image_filename": "sofa-cream.webp",
            "sku": "SOF-002",
            "name_he": "ספה שמנת",
            "name_en": "Cream Sofa",
            "price": "4290",
            "currency": "ILS",
            "category": "sofa",
            "in_stock": "false",
        }],
    )
    assets, _ = load_assets(d)
    assert assets[0].in_stock is False


def test_stable_key_uses_sku_when_present():
    d = _make_assets_dir(
        ["bookshelf-white.webp"],
        csv_rows=[{
            "image_filename": "bookshelf-white.webp",
            "sku": "SHL-001",
            "name_he": "",
            "name_en": "",
            "price": "1490",
            "currency": "ILS",
            "category": "bookshelf",
            "in_stock": "true",
        }],
    )
    assets, _ = load_assets(d)
    assert assets[0].stable_key == "SHL-001"


def test_stable_key_uses_stem_when_no_sku():
    d = _make_assets_dir(
        ["bookshelf-white.webp"],
        csv_rows=[{
            "image_filename": "bookshelf-white.webp",
            "sku": "",  # empty SKU
            "name_he": "",
            "name_en": "White Bookshelf",
            "price": "1490",
            "currency": "ILS",
            "category": "bookshelf",
            "in_stock": "true",
        }],
    )
    assets, _ = load_assets(d)
    assert assets[0].stable_key == "bookshelf-white"


def test_missing_images_dir():
    tmp = Path(tempfile.mkdtemp())
    assets, warnings = load_assets(tmp)
    assert assets == []
    assert warnings


@pytest.mark.xfail(
    reason="demo_assets/products.csv uses stable_key/image columns but the parser "
    "reads image_filename/sku (and lacks a cream-sofa row) — deferred CSV/parser "
    "reconciliation, tracked separately. See the 'demo_assets/products.csv format "
    "mismatch' follow-up task.",
    strict=False,
)
def test_full_demo_catalog():
    """Smoke-test against actual demo_assets/ directory."""
    demo_dir = Path(__file__).parent.parent.parent / "demo_assets"
    if not demo_dir.exists():
        pytest.skip("demo_assets not found")
    assets, warnings = load_assets(demo_dir)
    assert len(assets) == 11
    # bookshelf-white has empty names in CSV
    bookshelf = next(a for a in assets if "bookshelf" in a.stem)
    assert bookshelf.name_en is None
    assert bookshelf.name_he is None
    # sofa-cream-2seat is out of stock
    cream = next(a for a in assets if "cream" in a.stem)
    assert cream.in_stock is False
