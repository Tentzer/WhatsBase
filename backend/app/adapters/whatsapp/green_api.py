"""Green API implementation of the WhatsApp adapter.

This is the ONLY file in the codebase that may import whatsapp_api_client_python
or reference Green API payload shapes. All caller code uses base.WhatsAppAdapter
and base.IncomingMessage.

The Green API Python client is synchronous; every call is wrapped in
asyncio.to_thread so the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging

from whatsapp_api_client_python import API

from .base import IncomingMessage, MessageType, WhatsAppAdapter

logger = logging.getLogger(__name__)


class GreenApiAdapter(WhatsAppAdapter):
    def __init__(self, instance_id: str, token: str) -> None:
        self._instance_id = instance_id
        self._client = API.GreenApi(instance_id, token)

    # ------------------------------------------------------------------
    # Normalisation helpers (also used by the webhook router)
    # ------------------------------------------------------------------

    def normalize_polling_notification(self, notification: dict) -> IncomingMessage | None:
        """Parse a receiveNotification() response into an IncomingMessage.

        Returns None for non-message webhooks (status updates, etc.) so the
        poller can safely ack and discard them.
        """
        body = notification.get("body") or {}
        if body.get("typeWebhook") != "incomingMessageReceived":
            return None
        return self._parse_body(
            body=body,
            notification_id=notification.get("receiptId"),
        )

    def normalize_webhook_payload(self, body: dict) -> IncomingMessage | None:
        """Parse a Green API webhook POST body into an IncomingMessage.

        Webhook mode: the HTTP body IS the notification body (no outer
        receiptId wrapper; ack is implicit — just return 200).
        """
        if body.get("typeWebhook") != "incomingMessageReceived":
            return None
        return self._parse_body(body=body, notification_id=None)

    def _parse_body(self, body: dict, notification_id: int | None) -> IncomingMessage | None:
        message_data = body.get("messageData") or {}
        sender_data = body.get("senderData") or {}
        msg_type: str = message_data.get("typeMessage", "")
        message_id: str = body.get("idMessage", "")
        chat_id: str = sender_data.get("chatId", "")
        sender: str = sender_data.get("sender", chat_id)

        if msg_type in ("textMessage", "extendedTextMessage"):
            # Modern WhatsApp clients send plain text as extendedTextMessage
            # (any message with link preview, formatting, or reply context).
            if msg_type == "textMessage":
                text = (message_data.get("textMessageData") or {}).get("textMessage", "")
            else:
                text = (message_data.get("extendedTextMessageData") or {}).get("text", "")
            return IncomingMessage(
                instance_id=self._instance_id,
                message_id=message_id,
                chat_id=chat_id,
                sender=sender,
                type="text",
                text=text,
                notification_id=notification_id,
                raw=body,
            )

        if msg_type == "imageMessage":
            file_data = message_data.get("fileMessageData") or {}
            return IncomingMessage(
                instance_id=self._instance_id,
                message_id=message_id,
                chat_id=chat_id,
                sender=sender,
                type="image",
                media_url=file_data.get("downloadUrl"),
                caption=file_data.get("caption", ""),
                notification_id=notification_id,
                raw=body,
            )

        # Extended/quoted/other message types — return "other" so the
        # conversation agent can decide how to handle them later.
        if message_id:
            return IncomingMessage(
                instance_id=self._instance_id,
                message_id=message_id,
                chat_id=chat_id,
                sender=sender,
                type="other",
                notification_id=notification_id,
                raw=body,
            )

        return None

    # ------------------------------------------------------------------
    # Adapter interface
    # ------------------------------------------------------------------

    async def get_incoming(self) -> list[IncomingMessage]:
        """Receive one notification from the Green API queue.

        Returns a list with 0 or 1 items: 0 = queue empty or non-message
        event; 1 = one parsed IncomingMessage.  The caller is responsible for
        calling ack() after processing.
        """
        response = await asyncio.to_thread(self._client.receiving.receiveNotification)
        if response is None or response.code != 200 or not response.data:
            return []
        msg = self.normalize_polling_notification(response.data)
        if msg is None:
            # Non-message notification — ack it and drop.
            receipt_id = (response.data or {}).get("receiptId")
            if receipt_id is not None:
                await self.ack(receipt_id)
            return []
        return [msg]

    async def ack(self, notification_id: int) -> None:
        await asyncio.to_thread(
            self._client.receiving.deleteNotification, notification_id
        )

    async def send_text(self, chat_id: str, text: str) -> None:
        response = await asyncio.to_thread(
            self._client.sending.sendMessage, chat_id, text
        )
        if response is None or response.code not in (200, 201):
            logger.warning(
                "send_text to %s may have failed: status=%s",
                chat_id,
                response.code if response else "no-response",
            )

    async def send_image(self, chat_id: str, image_url: str, caption: str = "") -> None:
        filename = image_url.rsplit("/", 1)[-1] or "image.jpg"
        response = await asyncio.to_thread(
            self._client.sending.sendFileByUrl, chat_id, image_url, filename, caption
        )
        if response is None or response.code not in (200, 201):
            logger.warning(
                "send_image to %s may have failed: status=%s",
                chat_id,
                response.code if response else "no-response",
            )
