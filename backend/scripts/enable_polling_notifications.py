"""Enable Green API notification flags needed for polling to receive messages.

For polling intake mode, Green API still requires the notification queue to
be enabled (the flag is unfortunately named 'incomingWebhook'). Without
these, receiveNotification always returns nothing.
"""

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

    client = API.GreenApi(inst.green_api_instance_id, token)

    new_settings = {
        "incomingWebhook": "yes",
        "outgoingMessageWebhook": "yes",
        "outgoingAPIMessageWebhook": "yes",
        "stateWebhook": "yes",
    }

    print(f"Calling setSettings with: {new_settings}")
    r = await asyncio.to_thread(client.account.setSettings, new_settings)
    print(f"setSettings -> code={r.code}  data={r.data}  error={r.error}")

    print("\nVerifying via getSettings...")
    r2 = await asyncio.to_thread(client.account.getSettings)
    if r2.data:
        for key in new_settings:
            print(f"  {key} = {r2.data.get(key)!r}")


if __name__ == "__main__":
    asyncio.run(main())
