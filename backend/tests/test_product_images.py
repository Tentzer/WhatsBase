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


def test_validate_image_upload_rejects_non_images():
    with pytest.raises(ValueError, match="Unsupported image type"):
        validate_image_upload("notes.txt", "text/plain", 100)


def test_validate_image_upload_rejects_oversized_files():
    with pytest.raises(ValueError, match="too large"):
        validate_image_upload("big.jpg", "image/jpeg", 16 * 1024 * 1024)
