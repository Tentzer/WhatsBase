"""Supabase Storage helpers for owner-uploaded product photos during onboarding."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

BUCKET = "product-images"
MAX_IMAGE_BYTES = 15 * 1024 * 1024
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}


def sanitize_filename(name: str) -> str:
    """Strip path components and keep a safe basename for Storage keys."""
    stem = Path(name).name
    safe = re.sub(r"[^\w.\-]", "_", stem, flags=re.ASCII)
    return safe or "image.jpg"


def build_upload_storage_path(tenant_id: str, filename: str) -> str:
    """Tenant-scoped path for photos uploaded before a product row exists."""
    safe = sanitize_filename(filename)
    unique = uuid.uuid4().hex[:12]
    return f"{tenant_id}/uploads/{unique}_{safe}"


def guess_mime_type(filename: str, content_type: str | None) -> str:
    if content_type and content_type.startswith("image/"):
        return content_type
    suffix = Path(filename).suffix.lstrip(".").lower()
    if suffix == "jpg":
        suffix = "jpeg"
    return f"image/{suffix}" if suffix else "application/octet-stream"


def validate_image_upload(filename: str, content_type: str | None, size: int) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported image type: {suffix or 'unknown'}")
    if content_type and not content_type.startswith("image/"):
        raise ValueError("File must be an image")
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f"Image too large (max {MAX_IMAGE_BYTES // (1024 * 1024)} MB)")


def stable_key_from_upload_object_name(name: str) -> str:
    """Derive a product stable_key from a Storage object under uploads/."""
    match = re.match(r"^[0-9a-f]{12}_(.+)$", name, re.IGNORECASE)
    base_name = match.group(1) if match else name
    return Path(base_name).stem.lower()


async def list_orphan_tenant_uploads(
    tenant_id: str,
    linked_paths: set[str],
) -> list[tuple[str, str]]:
    """Return (storage_path, object_name) for upload images not linked to products."""
    try:
        from app.core.supabase import get_supabase

        supabase = get_supabase()
        prefix = f"{tenant_id}/uploads"

        def _list() -> list:
            return supabase.storage.from_(BUCKET).list(prefix)

        entries = await asyncio.to_thread(_list)
    except Exception as exc:
        logger.warning("unable to list tenant uploads for tenant=%s: %s", tenant_id, exc)
        return []

    orphans: list[tuple[str, str]] = []
    for entry in entries or []:
        name = getattr(entry, "name", None) or (entry.get("name") if isinstance(entry, dict) else None)
        if not name or name.endswith("/"):
            continue
        storage_path = f"{prefix}/{name}"
        if storage_path in linked_paths:
            continue
        orphans.append((storage_path, name))
    return orphans


async def public_url_for_storage_path(storage_path: str) -> str | None:
    try:
        from app.core.supabase import get_supabase

        supabase = get_supabase()

        def _url() -> str:
            return supabase.storage.from_(BUCKET).get_public_url(storage_path)

        return await asyncio.to_thread(_url)
    except Exception as exc:
        logger.warning("unable to resolve public url for %s: %s", storage_path, exc)
        return None


async def upload_owner_image(
    tenant_id: str,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> tuple[str, str]:
    """Upload bytes to Supabase Storage. Returns (storage_path, public_url)."""
    validate_image_upload(filename, content_type, len(content))
    storage_path = build_upload_storage_path(tenant_id, filename)
    mime = guess_mime_type(filename, content_type)

    from app.core.supabase import get_supabase

    supabase = get_supabase()
    await asyncio.to_thread(_ensure_bucket, supabase, BUCKET)

    def _upload() -> str:
        supabase.storage.from_(BUCKET).upload(
            storage_path,
            content,
            {"content-type": mime, "upsert": "true"},
        )
        return supabase.storage.from_(BUCKET).get_public_url(storage_path)

    public_url = await asyncio.to_thread(_upload)
    logger.info("uploaded owner image: %s", storage_path)
    return storage_path, public_url


def _ensure_bucket(supabase, bucket_name: str) -> None:
    """Create the public Storage bucket if it doesn't exist."""
    try:
        result = supabase.storage.get_bucket(bucket_name)
        is_public = getattr(result, "public", False)
        if not is_public:
            raise RuntimeError(
                f"Storage bucket '{bucket_name}' exists but is not public. "
                "Set it to public in the Supabase dashboard before uploading photos."
            )
    except Exception as exc:
        if "not found" in str(exc).lower() or "does not exist" in str(exc).lower():
            supabase.storage.create_bucket(bucket_name, options={"public": True})
            logger.info("Created public Storage bucket: %s", bucket_name)
        elif "not public" in str(exc):
            raise
        else:
            raise
