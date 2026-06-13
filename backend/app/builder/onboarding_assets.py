"""Materialize onboarding wizard data (DB + Storage) into a local assets folder.

The full Builder agent (builder/agent.py) expects a directory layout compatible
with the CLI flow: images/, optional products.csv, optional business_info.txt.
The site Build button stages tenant rows here, then runs the agent loop.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.product_images import BUCKET
from app.core.schema import BusinessInfo, Product, ProductImage

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@dataclass
class StagedProduct:
    stable_key: str
    name_he: str
    name_en: str
    category: str
    price: float
    currency: str
    in_stock: bool
    colors: str
    materials: str
    style: str
    image_filename: str
    storage_path: str | None = None
    public_url: str | None = None


def write_business_info_txt(rows: list[BusinessInfo], dest: Path) -> None:
    lines = [
        "# Business information exported from onboarding wizard.",
        "# Format: TOPIC | HE | EN",
        "",
    ]
    for row in rows:
        topic = (row.topic or "other").strip()
        content_he = (row.content_he or "").replace("\n", " ").strip()
        content_en = (row.content_en or "").replace("\n", " ").strip()
        if content_he or content_en:
            lines.append(f"{topic} | {content_he} | {content_en}")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_products_csv(products: list[StagedProduct], dest: Path) -> None:
    fieldnames = [
        "stable_key",
        "name_he",
        "name_en",
        "category",
        "price",
        "currency",
        "in_stock",
        "colors",
        "materials",
        "style",
        "image",
    ]
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for product in products:
            writer.writerow(
                {
                    "stable_key": product.stable_key,
                    "name_he": product.name_he,
                    "name_en": product.name_en,
                    "category": product.category,
                    "price": product.price,
                    "currency": product.currency,
                    "in_stock": str(product.in_stock).lower(),
                    "colors": product.colors,
                    "materials": product.materials,
                    "style": product.style,
                    "image": product.image_filename,
                }
            )


def _local_image_name(stable_key: str, storage_path: str | None, fallback: str) -> str:
    suffix = Path(storage_path or fallback).suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        suffix = Path(fallback).suffix.lower() or ".jpg"
    safe_key = stable_key.replace("/", "_").replace("\\", "_")
    return f"{safe_key}{suffix}"


async def _download_bytes(
    *,
    storage_path: str | None,
    public_url: str | None,
) -> bytes | None:
    if public_url:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(public_url)
                response.raise_for_status()
                return response.content
        except Exception as exc:
            logger.warning("download via public_url failed (%s): %s", public_url, exc)

    if not storage_path:
        return None

    try:
        from app.core.supabase import get_supabase

        supabase = get_supabase()

        def _download() -> bytes:
            return supabase.storage.from_(BUCKET).download(storage_path)

        return await asyncio.to_thread(_download)
    except Exception as exc:
        logger.warning("download via storage_path failed (%s): %s", storage_path, exc)
        return None


async def _list_orphan_uploads(tenant_id: str, linked_paths: set[str]) -> list[tuple[str, str]]:
    from app.core.product_images import list_orphan_tenant_uploads

    return await list_orphan_tenant_uploads(tenant_id, linked_paths)


async def materialize_tenant_assets(session: AsyncSession, tenant_id: str) -> Path:
    """Download tenant catalog data to a temp assets directory.

    Returns the temp directory path. Caller must delete it when done.
    Raises ValueError when there is nothing to build from.
    """
    products_result = await session.execute(
        select(Product)
        .where(Product.tenant_id == tenant_id)
        .options(selectinload(Product.images))
        .order_by(Product.created_at.asc())
    )
    products = products_result.scalars().all()

    bi_result = await session.execute(
        select(BusinessInfo)
        .where(BusinessInfo.tenant_id == tenant_id)
        .order_by(BusinessInfo.created_at.asc())
    )
    business_rows = bi_result.scalars().all()

    assets_dir = Path(tempfile.mkdtemp(prefix=f"whatsbase-build-{tenant_id[:8]}-"))
    images_dir = assets_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    staged_products: list[StagedProduct] = []
    linked_paths: set[str] = set()
    used_names: set[str] = set()

    for product in products:
        image: ProductImage | None = product.images[0] if product.images else None
        attrs = product.attributes or {}
        colors = attrs.get("colors", "")
        materials = attrs.get("materials", "")
        style = attrs.get("style", "")
        if isinstance(colors, list):
            colors = ", ".join(str(c) for c in colors)
        if isinstance(materials, list):
            materials = ", ".join(str(m) for m in materials)

        fallback_name = f"{product.stable_key}.jpg"
        image_filename = _local_image_name(
            product.stable_key,
            image.storage_path if image else None,
            fallback_name,
        )
        while image_filename in used_names:
            stem = Path(image_filename).stem
            suffix = Path(image_filename).suffix
            image_filename = f"{stem}_{len(used_names)}{suffix}"
        used_names.add(image_filename)

        if image is not None:
            linked_paths.add(image.storage_path)
            content = await _download_bytes(
                storage_path=image.storage_path,
                public_url=image.public_url,
            )
            if content:
                (images_dir / image_filename).write_bytes(content)
            else:
                logger.warning(
                    "skipped image download for product %s (%s)",
                    product.stable_key,
                    image.storage_path,
                )

        staged_products.append(
            StagedProduct(
                stable_key=product.stable_key,
                name_he=product.name_he or "",
                name_en=product.name_en or "",
                category=product.category or "",
                price=float(product.price or 0),
                currency=product.currency or "ILS",
                in_stock=bool(product.in_stock),
                colors=str(colors),
                materials=str(materials),
                style=str(style),
                image_filename=image_filename if image is not None else "",
                storage_path=image.storage_path if image else None,
                public_url=image.public_url if image else None,
            )
        )

    orphan_uploads = await _list_orphan_uploads(tenant_id, linked_paths)
    for storage_path, storage_name in orphan_uploads:
        stem = Path(storage_name).stem.lower()
        stable_key = stem
        suffix = Path(storage_name).suffix.lower() or ".jpg"
        image_filename = f"{stable_key}{suffix}"
        while image_filename in used_names:
            image_filename = f"{stable_key}_{len(used_names)}{suffix}"
        used_names.add(image_filename)

        content = await _download_bytes(storage_path=storage_path, public_url=None)
        if not content:
            continue
        (images_dir / image_filename).write_bytes(content)
        staged_products.append(
            StagedProduct(
                stable_key=stable_key,
                name_he="",
                name_en="",
                category="",
                price=0.0,
                currency="ILS",
                in_stock=True,
                colors="",
                materials="",
                style="",
                image_filename=image_filename,
                storage_path=storage_path,
            )
        )

    image_count = len(list(images_dir.iterdir()))
    if image_count == 0 and not staged_products:
        shutil.rmtree(assets_dir, ignore_errors=True)
        raise ValueError(
            "No product images found. Upload photos in step 2 and save before building."
        )

    if staged_products:
        write_products_csv(
            [p for p in staged_products if p.image_filename],
            assets_dir / "products.csv",
        )
    if business_rows:
        write_business_info_txt(business_rows, assets_dir / "business_info.txt")

    logger.info(
        "materialized tenant assets: tenant=%s images=%d products=%d business_info=%d dir=%s",
        tenant_id,
        image_count,
        len(staged_products),
        len(business_rows),
        assets_dir,
    )
    return assets_dir
