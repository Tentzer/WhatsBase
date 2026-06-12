"""Builder tools: caption_image, create_or_update_product."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from functools import lru_cache

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.builder.context import BuildContext
from app.core.config import get_settings
from app.core.models import get_model
from app.core.schema import Product, ProductImage

logger = logging.getLogger(__name__)

_CAPTION_PROMPT = """\
Caption this furniture product image. Return JSON with these exact fields:
- name_he: product name in Hebrew (concise, 2-5 words)
- name_en: product name in English (concise, 2-5 words)
- category: single lowercase word (sofa/chair/table/bed/lamp/shelf/nightstand/other)
- colors: JSON array of color strings (lowercase English)
- materials: JSON array of material strings (lowercase English)
- style: one of: modern/classic/industrial/scandinavian/minimalist/other
- description_he: 1-2 sentence Hebrew description for a customer
- description_en: 1-2 sentence English description for a customer

Respond with ONLY valid JSON, no markdown, no extra text."""


@lru_cache(maxsize=1)
def _get_openai():
    from langfuse.openai import OpenAI  # drop-in: auto-tracks model/tokens as Langfuse generation

    return OpenAI(api_key=get_settings().openai_api_key)


async def caption_image(ctx: BuildContext, filename: str) -> str:
    """Caption a product image. Returns JSON string with structured product data."""
    image_path = ctx.assets_dir / "images" / filename
    if not image_path.exists():
        return json.dumps({"error": f"Image not found: {filename}"})

    with image_path.open("rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode()

    suffix = image_path.suffix.lstrip(".").lower()
    mime = "image/webp" if suffix == "webp" else f"image/{suffix}"
    data_url = f"data:{mime};base64,{b64}"

    model_cfg = get_model("vision")
    client = _get_openai()

    def _call() -> dict:
        resp = client.chat.completions.create(
            model=model_cfg.name,
            max_tokens=model_cfg.max_tokens or 1024,
            temperature=model_cfg.temperature or 0.0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": _CAPTION_PROMPT},
                    ],
                }
            ],
        )
        raw_text = resp.choices[0].message.content or "{}"
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("caption_image: invalid JSON from vision model for %s", filename)
            return {"name_en": filename.split(".")[0], "name_he": "", "category": "other",
                    "colors": [], "materials": [], "style": "other",
                    "description_en": "", "description_he": ""}

    caption = await asyncio.to_thread(_call)
    ctx.report.found.append(filename)
    logger.info("captioned: %s → %s", filename, caption.get("name_en", "?"))
    return json.dumps(caption)


async def create_or_update_product(ctx: BuildContext, data: dict) -> str:
    """Upsert a product + upload its image. Returns product_id."""
    tenant_id = ctx.tenant_id

    stable_key = data.get("stable_key") or data.get("stem") or data.get("filename", "unknown").split(".")[0].lower()
    name_he = data.get("name_he") or None
    name_en = data.get("name_en") or None
    description_he = data.get("description_he") or None
    description_en = data.get("description_en") or None
    category = data.get("category") or None
    price = data.get("price")
    if price is not None:
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = None
    currency = data.get("currency") or "ILS"
    in_stock_raw = data.get("in_stock", True)
    if isinstance(in_stock_raw, str):
        in_stock = in_stock_raw.lower() not in {"false", "0", "no"}
    else:
        in_stock = bool(in_stock_raw)
    colors = data.get("colors") or []
    materials = data.get("materials") or []
    style = data.get("style") or None
    attributes = {"colors": colors, "materials": materials, "style": style}
    caption_he = data.get("caption_he") or description_he
    caption_en = data.get("caption_en") or description_en

    # Detect assumptions: if the original CSV row lacked a name but one arrived, it came from caption.
    original = ctx.assets.get(stable_key)
    if original is not None:
        if not original.name_he and name_he:
            ctx.report.assumed.append(
                f"{stable_key}: name_he absent in CSV, generated from caption: {name_he!r}"
            )
        if not original.name_en and name_en:
            ctx.report.assumed.append(
                f"{stable_key}: name_en absent in CSV, generated from caption: {name_en!r}"
            )

    if ctx.dry_run:
        logger.info(
            "[dry-run] would upsert product: %s  name_en=%r  category=%r  price=%s  in_stock=%s  colors=%s",
            stable_key, name_en, category, price, in_stock, colors,
        )
        ctx.report.created.append(stable_key)
        return json.dumps({"product_id": f"dry-{stable_key}", "stable_key": stable_key, "dry_run": True})

    session = ctx.session

    # Upsert product by (tenant_id, stable_key).
    stmt = (
        pg_insert(Product)
        .values(
            tenant_id=tenant_id,
            stable_key=stable_key,
            name_he=name_he,
            name_en=name_en,
            description_he=description_he,
            description_en=description_en,
            category=category,
            attributes=attributes,
            price=price,
            currency=currency,
            in_stock=in_stock,
            source="owner_input",
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "stable_key"],
            set_={
                "name_he": name_he,
                "name_en": name_en,
                "description_he": description_he,
                "description_en": description_en,
                "category": category,
                "attributes": attributes,
                "price": price,
                "currency": currency,
                "in_stock": in_stock,
            },
        )
        .returning(Product.id)
    )
    result = await session.execute(stmt)
    product_id = str(result.scalar_one())

    # Image upload + product_images row.
    filename = data.get("filename")
    if filename:
        storage_path = f"{tenant_id}/{stable_key}/{filename}"
        public_url: str | None = None

        if not ctx.dry_run:
            public_url = await _upload_image(ctx, filename, storage_path)

        # Replace any existing product_images row for this product.
        await session.execute(
            delete(ProductImage).where(ProductImage.product_id == product_id)
        )
        session.add(
            ProductImage(
                product_id=product_id,
                storage_path=storage_path,
                public_url=public_url,
                caption_he=caption_he,
                caption_en=caption_en,
            )
        )

    await session.commit()
    ctx.report.created.append(stable_key)
    logger.info("upserted product: %s (id=%s)", stable_key, product_id)
    return json.dumps({"product_id": product_id, "stable_key": stable_key})


async def _upload_image(ctx: BuildContext, filename: str, storage_path: str) -> str | None:
    """Upload image file to Supabase Storage. Returns public URL or None on failure."""
    image_path = ctx.assets_dir / "images" / filename
    if not image_path.exists():
        logger.warning("Image not found for upload: %s", filename)
        return None

    try:
        from app.core.supabase import get_supabase

        supabase = get_supabase()
        bucket = "product-images"

        # Ensure bucket exists and is public.
        await asyncio.to_thread(_ensure_bucket, supabase, bucket)

        suffix = image_path.suffix.lstrip(".").lower()
        mime = "image/webp" if suffix == "webp" else f"image/{suffix}"

        with image_path.open("rb") as f:
            content = f.read()

        def _upload():
            supabase.storage.from_(bucket).upload(
                storage_path,
                content,
                {"content-type": mime, "upsert": "true"},
            )
            return supabase.storage.from_(bucket).get_public_url(storage_path)

        public_url = await asyncio.to_thread(_upload)
        logger.info("uploaded: %s", storage_path)
        return public_url
    except Exception as exc:
        logger.error("upload failed for %s: %s", filename, exc)
        ctx.report.errors.append(f"Upload failed for {filename}: {exc}")
        return None


def _ensure_bucket(supabase, bucket_name: str) -> None:
    """Create the public Storage bucket if it doesn't exist."""
    try:
        result = supabase.storage.get_bucket(bucket_name)
        # The result is a BucketResponse; check public attr.
        is_public = getattr(result, "public", False)
        if not is_public:
            raise RuntimeError(
                f"Storage bucket '{bucket_name}' exists but is not public. "
                "Set it to public in the Supabase dashboard before running a build."
            )
    except Exception as exc:
        # get_bucket raises when the bucket doesn't exist.
        if "not found" in str(exc).lower() or "does not exist" in str(exc).lower():
            supabase.storage.create_bucket(bucket_name, options={"public": True})
            logger.info("Created public Storage bucket: %s", bucket_name)
        elif "not public" in str(exc):
            raise
        else:
            # Unexpected error — re-raise so the caller sees it.
            raise
