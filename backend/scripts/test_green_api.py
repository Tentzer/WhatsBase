"""One-off diagnostic — call Green API getSettings directly."""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from whatsapp_api_client_python import API

from app.core.config import get_settings
from app.core.crypto import decrypt_token
from app.core.db import SessionLocal
from app.core.schema import WhatsAppInstance


async def main() -> None:
    s = get_settings()
    async with SessionLocal() as session:
        inst = (await session.execute(select(WhatsAppInstance))).scalars().first()
        token = decrypt_token(inst.token_encrypted, s.token_encryption_key)
    print(f"instance_id={inst.green_api_instance_id}  token_len={len(token)}")

    client = API.GreenApi(inst.green_api_instance_id, token)
    print("Calling getSettings...")
    r = await asyncio.to_thread(client.account.getSettings)
    print(f"code={r.code}")
    print(f"data={r.data}")
    print(f"error={r.error}")

    print("\nCalling getStateInstance...")
    r2 = await asyncio.to_thread(client.account.getStateInstance)
    print(f"code={r2.code}")
    print(f"data={r2.data}")
    print(f"error={r2.error}")


if __name__ == "__main__":
    asyncio.run(main())
