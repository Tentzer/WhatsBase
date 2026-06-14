from __future__ import annotations

import pytest

from app.core.product_images import (
    build_upload_storage_path,
    sanitize_filename,
    validate_image_upload,
)


def test_sanitize_filename_strips_directories():
    assert sanitize_filename("../../evil/photo.jpg") == "photo.jpg"


def test_build_upload_storage_path_is_tenant_scoped():
    path = build_upload_storage_path("tenant-1", "sofa-white.webp")
    assert path.startswith("tenant-1/uploads/")
    assert path.endswith("_sofa-white.webp")


def test_build_public_storage_url(monkeypatch):
    from app.core.config import Settings
    from app.core.product_images import BUCKET, build_public_storage_url

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(supabase_url="https://example.supabase.co"),
    )
    url = build_public_storage_url("tenant-1/uploads/abc_bed.jpg")
    assert (
        url
        == f"https://example.supabase.co/storage/v1/object/public/{BUCKET}/tenant-1/uploads/abc_bed.jpg"
    )


def test_stable_key_from_upload_object_name_strips_uuid_prefix():
    from app.core.product_images import stable_key_from_upload_object_name

    assert (
        stable_key_from_upload_object_name("abc123def456_bed-america-black-mattress-gift.jpg")
        == "bed-america-black-mattress-gift"
    )


def test_validate_image_upload_rejects_non_images():
    with pytest.raises(ValueError, match="Unsupported image type"):
        validate_image_upload("notes.txt", "text/plain", 100)


def test_validate_image_upload_rejects_oversized_files():
    with pytest.raises(ValueError, match="too large"):
        validate_image_upload("big.jpg", "image/jpeg", 16 * 1024 * 1024)
