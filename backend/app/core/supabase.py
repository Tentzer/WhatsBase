"""Supabase client wrapper — Storage (product images) and Auth (token verify).

The backend uses the SERVICE key and therefore bypasses RLS; RLS policies in
the migration exist for the frontend, which talks to Supabase with the anon key.
The client is created lazily so importing this module never requires live keys.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from supabase import Client


@lru_cache
def get_supabase() -> "Client":
    """Service-role Supabase client (Storage + admin). Bypasses RLS.

    Imported lazily so importing this module doesn't require the supabase SDK
    (keeps the import graph light for tests and tooling)."""
    from supabase import create_client

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError(
            "Supabase is not configured: set SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
    return create_client(settings.supabase_url, settings.supabase_service_key)
