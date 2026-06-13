"""Product image helpers — Supabase Storage URLs and backfill.

Photos often exist in the `product-images` bucket while `product_images.public_url`
still holds a stale blob: URL or `mock/uploads/...` path from the onboarding UI.
These helpers resolve a usable public URL at read time and can persist fixes.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)

PRODUCT_IMAGES_BUCKET = "product-images"
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_ALLOWED_MIME_PREFIXES = ("image/jpeg", "image/png", "image/webp", "image/gif")


def is_usable_public_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def public_url_for_storage_path(storage_path: str) -> str:
    from app.core.supabase import get_supabase

    supabase = get_supabase()
    return supabase.storage.from_(PRODUCT_IMAGES_BUCKET).get_public_url(storage_path)


def _list_folder(supabase: "Client", prefix: str) -> list[dict]:
    try:
        result = supabase.storage.from_(PRODUCT_IMAGES_BUCKET).list(prefix)
        return result or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("storage list failed for %s: %s", prefix, exc)
        return []


def discover_storage_object_path(
    tenant_id: str,
    stable_key: str,
    *,
    filename_hint: str | None = None,
) -> str | None:
    """Locate a product image object already stored under the tenant prefix."""
    from app.core.supabase import get_supabase

    supabase = get_supabase()
    candidates: list[str] = []

    product_prefix = f"{tenant_id}/{stable_key}"
    for entry in _list_folder(supabase, product_prefix):
        name = entry.get("name")
        if not name or name.endswith("/"):
            continue
        candidates.append(f"{product_prefix}/{name}")

    if filename_hint:
        hint = filename_hint.strip()
        for path in candidates:
            if path.endswith(f"/{hint}") or path.endswith(hint):
                return path
        candidates.append(f"{product_prefix}/{hint}")

    uploads_prefix = f"{tenant_id}/uploads"
    for entry in _list_folder(supabase, uploads_prefix):
        name = entry.get("name")
        if not name or name.endswith("/"):
            continue
        if filename_hint and filename_hint not in name:
            continue
        candidates.append(f"{uploads_prefix}/{name}")

    for path in candidates:
        if not path.startswith("mock/"):
            return path

    tenant_entries = _list_folder(supabase, tenant_id)
    for entry in tenant_entries:
        name = entry.get("name")
        if not name:
            continue
        if name == stable_key or stable_key in name:
            nested = _list_folder(supabase, f"{tenant_id}/{name}")
            for child in nested:
                child_name = child.get("name")
                if child_name and not child_name.endswith("/"):
                    return f"{tenant_id}/{name}/{child_name}"

    return candidates[0] if candidates else None


def resolve_product_image_url(
    *,
    tenant_id: str,
    stable_key: str,
    storage_path: str | None,
    public_url: str | None,
    filename_hint: str | None = None,
) -> str | None:
    """Return the best public URL for a product image."""
    if is_usable_public_url(public_url):
        return public_url

    if storage_path and not storage_path.startswith("mock/"):
        return public_url_for_storage_path(storage_path)

    hint = filename_hint
    if not hint and storage_path:
        hint = storage_path.rsplit("/", 1)[-1]

    discovered = discover_storage_object_path(
        tenant_id,
        stable_key,
        filename_hint=hint,
    )
    if discovered:
        return public_url_for_storage_path(discovered)

    return None


def resolve_hit_image_urls(
    *,
    tenant_id: str,
    stable_key: str,
    image_records: list[dict],
) -> list[str]:
    """Resolve one or more displayable URLs from product_images rows."""
    urls: list[str] = []
    for record in image_records:
        resolved = resolve_product_image_url(
            tenant_id=tenant_id,
            stable_key=stable_key,
            storage_path=record.get("storage_path"),
            public_url=record.get("public_url"),
            filename_hint=record.get("file_name"),
        )
        if resolved and resolved not in urls:
            urls.append(resolved)
    return urls


async def upload_product_image(
    *,
    tenant_id: str,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> tuple[str, str]:
    """Upload bytes to Supabase Storage. Returns (storage_path, public_url)."""
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValueError("Image exceeds 5 MB limit")
    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if not any(mime.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
        raise ValueError("Only JPG, PNG, WebP, and GIF images are supported")

    safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1] or "product.jpg"
    storage_path = f"{tenant_id}/uploads/{uuid.uuid4().hex}_{safe_name}"

    from app.core.supabase import get_supabase
    from app.builder.tools.catalog import _ensure_bucket

    supabase = get_supabase()

    def _upload() -> str:
        _ensure_bucket(supabase, PRODUCT_IMAGES_BUCKET)
        supabase.storage.from_(PRODUCT_IMAGES_BUCKET).upload(
            storage_path,
            content,
            {"content-type": mime, "upsert": "true"},
        )
        return public_url_for_storage_path(storage_path)

    public_url = await asyncio.to_thread(_upload)
    return storage_path, public_url


def backfill_product_image_row(
    *,
    tenant_id: str,
    stable_key: str,
    storage_path: str | None,
    public_url: str | None,
    filename_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve URL and canonical storage path for a product_images row."""
    resolved_url = resolve_product_image_url(
        tenant_id=tenant_id,
        stable_key=stable_key,
        storage_path=storage_path,
        public_url=public_url,
        filename_hint=filename_hint,
    )
    resolved_path = storage_path
    if resolved_url and (not storage_path or storage_path.startswith("mock/")):
        settings = get_settings()
        base = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/public/{PRODUCT_IMAGES_BUCKET}/"
        if resolved_url.startswith(base):
            resolved_path = resolved_url[len(base) :]
        else:
            discovered = discover_storage_object_path(
                tenant_id,
                stable_key,
                filename_hint=filename_hint,
            )
            if discovered:
                resolved_path = discovered

    return resolved_path, resolved_url
