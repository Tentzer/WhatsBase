"""Delete all product-related data for a tenant (DB + Storage).

Usage:
    python -m scripts.purge_tenant_products tentzer@icloud.com

Removes products, product_images, product embeddings, build_runs, and all
objects under {tenant_id}/ in the product-images bucket. Resets agent status.
Does NOT delete business_info, conversations, or WhatsApp config.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import delete, select, update

from app.core.db import SessionLocal
from app.core.product_images import BUCKET
from app.core.schema import Agent, BuildRun, Embedding, Product, User

logger = logging.getLogger(__name__)


async def _list_storage_paths(prefix: str) -> list[str]:
    from app.core.supabase import get_supabase

    supabase = get_supabase()
    paths: list[str] = []
    page_size = 1000

    def _list_page(folder: str, offset: int) -> list:
        return supabase.storage.from_(BUCKET).list(
            folder,
            {"limit": page_size, "offset": offset, "sortBy": {"column": "name", "order": "asc"}},
        )

    def _list_all_files(folder: str) -> list[str]:
        found: list[str] = []
        offset = 0
        while True:
            entries = _list_page(folder, offset)
            if not entries:
                break
            for entry in entries:
                name = getattr(entry, "name", None) or (
                    entry.get("name") if isinstance(entry, dict) else None
                )
                if not name:
                    continue
                child = f"{folder}/{name}".replace("//", "/")
                metadata = getattr(entry, "metadata", None) or (
                    entry.get("metadata") if isinstance(entry, dict) else None
                )
                # Folder entries have null/empty metadata; files have size/mimetype.
                if metadata is None and "." not in name:
                    found.extend(_list_all_files(child))
                else:
                    found.append(child)
            if len(entries) < page_size:
                break
            offset += page_size
        return found

    paths.extend(await asyncio.to_thread(_list_all_files, prefix))
    return paths


async def _delete_storage_paths(paths: list[str]) -> int:
    if not paths:
        return 0
    from app.core.supabase import get_supabase

    supabase = get_supabase()
    deleted = 0
    batch_size = 100

    def _remove_batch(batch: list[str]) -> None:
        supabase.storage.from_(BUCKET).remove(batch)

    for start in range(0, len(paths), batch_size):
        batch = paths[start : start + batch_size]
        await asyncio.to_thread(_remove_batch, batch)
        deleted += len(batch)
    return deleted


async def purge(email: str) -> None:
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise SystemExit(f"No user found for email: {email}")
        if not user.tenant_id:
            raise SystemExit(f"User {email} has no tenant_id")

        tenant_id = str(user.tenant_id)
        print(f"Purging product data for tenant={tenant_id} user={email}")

        emb_result = await session.execute(
            delete(Embedding).where(
                Embedding.tenant_id == tenant_id,
                Embedding.ref_type == "product",
            )
        )
        embeddings_deleted = emb_result.rowcount or 0

        prod_result = await session.execute(
            delete(Product).where(Product.tenant_id == tenant_id)
        )
        products_deleted = prod_result.rowcount or 0

        build_result = await session.execute(
            delete(BuildRun).where(BuildRun.tenant_id == tenant_id)
        )
        builds_deleted = build_result.rowcount or 0

        await session.execute(
            update(Agent)
            .where(Agent.tenant_id == tenant_id)
            .values(status="building", system_prompt=None, version=1)
        )

        await session.commit()

    storage_paths = await _list_storage_paths(tenant_id)
    storage_deleted = await _delete_storage_paths(storage_paths)

    print(
        f"Done: products={products_deleted} embeddings={embeddings_deleted} "
        f"build_runs={builds_deleted} storage_files={storage_deleted}"
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Purge tenant product catalog data")
    parser.add_argument("email", help="Owner email (e.g. tentzer@icloud.com)")
    args = parser.parse_args()
    asyncio.run(purge(args.email))


if __name__ == "__main__":
    main()
