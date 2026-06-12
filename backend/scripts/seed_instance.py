"""Seed a demo tenant + WhatsApp instance row (M2 bootstrapping).

Reads GREEN_API_INSTANCE_ID and GREEN_API_TOKEN from backend/.env (via
Settings). Encrypts the token with TOKEN_ENCRYPTION_KEY before storing.
Idempotent: re-running will update the existing row, not duplicate it.

Run with:  python -m scripts.seed_instance   (from backend/)
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.core.db import SessionLocal
from app.core.schema import Tenant, WhatsAppInstance


async def seed() -> None:
    settings = get_settings()

    if not settings.green_api_instance_id:
        logger.error("GREEN_API_INSTANCE_ID is not set in backend/.env — aborting.")
        sys.exit(1)
    if not settings.green_api_token:
        logger.error("GREEN_API_TOKEN is not set in backend/.env — aborting.")
        sys.exit(1)
    if not settings.token_encryption_key:
        logger.error("TOKEN_ENCRYPTION_KEY is not set in backend/.env — aborting.")
        sys.exit(1)

    encrypted_token = encrypt_token(settings.green_api_token, settings.token_encryption_key)

    async with SessionLocal() as session:
        # --- Upsert demo tenant ---
        result = await session.execute(
            select(Tenant).where(Tenant.name == "Demo Furniture Store")
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name="Demo Furniture Store", status="active", plan="free")
            session.add(tenant)
            await session.flush()  # populate tenant.id
            logger.info("Created tenant id=%s", tenant.id)
        else:
            logger.info("Tenant already exists id=%s", tenant.id)

        # --- Upsert WhatsApp instance ---
        result = await session.execute(
            select(WhatsAppInstance).where(
                WhatsAppInstance.green_api_instance_id == settings.green_api_instance_id
            )
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            instance = WhatsAppInstance(
                tenant_id=tenant.id,
                green_api_instance_id=settings.green_api_instance_id,
                token_encrypted=encrypted_token,
                status="active",
                intake_mode=settings.intake_mode,
            )
            session.add(instance)
            logger.info(
                "Created whatsapp_instances row for instance_id=%s intake_mode=%s",
                settings.green_api_instance_id,
                settings.intake_mode,
            )
        else:
            # Update token in case it was rotated.
            instance.token_encrypted = encrypted_token
            instance.tenant_id = tenant.id
            instance.intake_mode = settings.intake_mode
            logger.info(
                "Updated whatsapp_instances row for instance_id=%s",
                settings.green_api_instance_id,
            )

        await session.commit()

        logger.info("Done — tenant_id=%s  instance_id=%s", tenant.id, instance.id)
        print(f"\n  tenant_id  = {tenant.id}")
        print(f"  instance_id = {instance.id}")
        print(f"  green_api_instance_id = {instance.green_api_instance_id}")
        print(f"  intake_mode = {instance.intake_mode}\n")


if __name__ == "__main__":
    asyncio.run(seed())
