from app.core.product_images import is_usable_public_url


def test_rejects_blob_urls():
    assert not is_usable_public_url("blob:https://whatsbase.vercel.app/abc")
    assert not is_usable_public_url(None)
    assert is_usable_public_url("https://example.supabase.co/storage/v1/object/public/product-images/a/b.jpg")
