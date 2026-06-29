"""Link an existing Supabase auth user to an existing tenant.

Use this when a tenant was seeded directly (bypassing the normal onboarding
flow) and needs to be associated with a Supabase auth user so the owner can
log in via the dashboard.

Run from the backend directory:

    cd C:\\Projects\\WhatsBase\\backend
    python scripts/link_user_to_tenant.py

The script is fully idempotent — re-running is safe and will not create
duplicate rows or modify any other user.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure the backend package is importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.schema import User

# ---------------------------------------------------------------------------
# Constants — edit these if you ever need to link a different user / tenant.
# ---------------------------------------------------------------------------
TENANT_ID = "7d82152f-57b2-49ec-8590-102fbcd8c652"   # EMS כפר סבא
SUPABASE_USER_ID = "9cad3a9c-aafb-42b3-8452-31c337276019"
USER_EMAIL = "eyal848@gmail.com"


async def main() -> None:
    async with SessionLocal() as session:

        result = await session.execute(
            select(User).where(User.supabase_user_id == SUPABASE_USER_ID)
        )
        user_row = result.scalar_one_or_none()

        if user_row is None:
            # No users row at all — INSERT one, matching what onboarding.py does.
            print(f"No users row found for supabase_user_id={SUPABASE_USER_ID}")
            print(f"Inserting new row → tenant {TENANT_ID} ...")
            user_row = User(
                tenant_id=TENANT_ID,
                supabase_user_id=SUPABASE_USER_ID,
                email=USER_EMAIL,
            )
            session.add(user_row)
            await session.flush()   # lets the DB assign id via gen_random_uuid()
            await session.commit()
            await session.refresh(user_row)
            print("INSERT done.")

        elif user_row.tenant_id == TENANT_ID:
            print(f"Already correctly linked — no write needed.")

        else:
            # Row exists but points to a different tenant — UPDATE it.
            old = user_row.tenant_id
            print(f"Found users row id={user_row.id}")
            print(f"  currently linked to: {old}")
            print(f"  updating tenant_id → {TENANT_ID} ...")
            user_row.tenant_id = TENANT_ID
            await session.commit()
            await session.refresh(user_row)
            print("UPDATE done.")

        # Read back and print for verification.
        print()
        print("=" * 60)
        print("users row (read back from DB):")
        print(f"  id               = {user_row.id}")
        print(f"  tenant_id        = {user_row.tenant_id}")
        print(f"  supabase_user_id = {user_row.supabase_user_id}")
        print(f"  email            = {user_row.email}")
        print(f"  created_at       = {user_row.created_at}")
        print("=" * 60)

        ok = (
            user_row.tenant_id == TENANT_ID
            and user_row.supabase_user_id == SUPABASE_USER_ID
            and user_row.email == USER_EMAIL
        )
        print()
        if ok:
            print("OK  eyal848@gmail.com is now linked to EMS tenant 7d82152f-...")
        else:
            print("MISMATCH — check the row above.")


if __name__ == "__main__":
    asyncio.run(main())
