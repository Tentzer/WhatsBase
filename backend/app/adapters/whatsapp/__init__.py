"""Adapter factory — the only import callers outside adapters/whatsapp/ need.

Usage::

    from app.adapters.whatsapp import get_adapter
    adapter = get_adapter(whatsapp_instance_orm_row)

The caller never imports GreenApiAdapter or any Green API type directly.
"""

from __future__ import annotations

from app.core.crypto import decrypt_token
from app.core.config import get_settings
from app.core.schema import WhatsAppInstance
from .base import WhatsAppAdapter


def get_adapter(instance: WhatsAppInstance) -> WhatsAppAdapter:
    """Return the correct adapter for a WhatsAppInstance row."""
    from .green_api import GreenApiAdapter  # lazy to keep import graph clean

    token = decrypt_token(instance.token_encrypted, get_settings().token_encryption_key)
    return GreenApiAdapter(instance.green_api_instance_id, token)
