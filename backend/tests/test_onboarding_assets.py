from __future__ import annotations

from pathlib import Path

from app.builder.assets import load_assets
from app.builder.onboarding_assets import StagedProduct, write_business_info_txt, write_products_csv
from app.core.schema import BusinessInfo


def test_write_products_csv_uses_stable_key(tmp_path: Path):
    products = [
        StagedProduct(
            stable_key="sofa-white",
            name_he="ספה",
            name_en="Sofa",
            category="sofa",
            price=3990.0,
            currency="ILS",
            in_stock=True,
            colors="white",
            materials="fabric",
            style="modern",
            image_filename="sofa-white.jpg",
        )
    ]
    csv_path = tmp_path / "products.csv"
    write_products_csv(products, csv_path)

    assets_dir = tmp_path
    (assets_dir / "images").mkdir()
    (assets_dir / "images" / "sofa-white.jpg").write_bytes(b"img")

    assets, _ = load_assets(assets_dir)
    assert len(assets) == 1
    assert assets[0].stable_key == "sofa-white"
    assert assets[0].name_en == "Sofa"
    assert assets[0].colors == "white"
    assert assets[0].csv_matched


def test_write_business_info_txt(tmp_path: Path):
    rows = [
        BusinessInfo(
            tenant_id="tenant-1",
            topic="hours",
            content_he="ראשון-חמישי 9-17",
            content_en="Sun-Thu 9-17",
        )
    ]
    dest = tmp_path / "business_info.txt"
    write_business_info_txt(rows, dest)
    text = dest.read_text(encoding="utf-8")
    assert "hours | ראשון-חמישי 9-17 | Sun-Thu 9-17" in text
