"""Generate labeled solid-color placeholder JPEGs for the demo catalog.

No network fetch — images are drawn with PIL. One image per row in products.csv,
named by the row's `image` column. Replace these with real furniture photos
before running the Builder agent in M3 (see README.md).

Usage (from demo_assets/):  python generate_placeholders.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
IMAGES_DIR = HERE / "images"
SIZE = (800, 800)

# Stable, readable color per category so placeholders are visually distinct.
CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "sofa": (120, 144, 156),
    "armchair": (141, 110, 99),
    "table": (161, 136, 127),
    "chair": (84, 110, 122),
    "storage": (96, 125, 139),
    "bed": (120, 130, 140),
    "lighting": (191, 160, 90),
}
DEFAULT_COLOR = (130, 130, 130)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw(label: str, price: str, color: tuple[int, int, int], out: Path) -> None:
    img = Image.new("RGB", SIZE, color)
    draw = ImageDraw.Draw(img)
    title_font = _font(48)
    price_font = _font(40)

    def centered(text: str, font, y: int) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        w = box[2] - box[0]
        draw.text(((SIZE[0] - w) / 2, y), text, fill=(255, 255, 255), font=font)

    centered(label, title_font, 330)
    centered(price, price_font, 410)
    draw.rectangle([20, 20, SIZE[0] - 20, SIZE[1] - 20], outline=(255, 255, 255), width=4)
    img.save(out, "JPEG", quality=85)


def main() -> None:
    IMAGES_DIR.mkdir(exist_ok=True)
    rows = list(csv.DictReader((HERE / "products.csv").open(encoding="utf-8")))
    for row in rows:
        category = row.get("category", "")
        color = CATEGORY_COLORS.get(category, DEFAULT_COLOR)
        label = row["name_en"]
        price = f"{row['price']} {row['currency']}"
        out = IMAGES_DIR / row["image"]
        _draw(label, price, color, out)
        print(f"wrote {out.relative_to(HERE)}")
    print(f"\n{len(rows)} placeholder images written to {IMAGES_DIR.relative_to(HERE)}/")


if __name__ == "__main__":
    main()
