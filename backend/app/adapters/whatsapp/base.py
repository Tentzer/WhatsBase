"""WhatsApp adapter interface — the boundary that keeps Green API internals
isolated. Everything outside adapters/whatsapp/ talks exclusively to these
abstractions (SPEC invariant #3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

MessageType = Literal["text", "image", "other"]


@dataclass
class IncomingMessage:
    instance_id: str    # green_api_instance_id string
    message_id: str     # Green API idMessage — used as idempotency key
    chat_id: str        # e.g. "972501234567@c.us"
    sender: str         # same as chat_id for direct messages
    type: MessageType
    text: str | None = None
    media_url: str | None = None
    caption: str | None = None
    # receiptId from polling — needed to call deleteNotification (ack).
    # None when the message arrived via webhook (ack = return 200).
    notification_id: int | None = None
    # Raw source payload kept for debugging; not used by the queue logic.
    raw: dict = field(default_factory=dict, compare=False, repr=False)


class WhatsAppAdapter(ABC):
    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> None: ...

    @abstractmethod
    async def send_image(self, chat_id: str, image_url: str, caption: str = "") -> None: ...

    @abstractmethod
    async def get_incoming(self) -> list[IncomingMessage]:
        """Poll for one pending notification. Returns 0 or 1 item."""
        ...

    @abstractmethod
    async def ack(self, notification_id: int) -> None:
        """Acknowledge (delete) a polled notification so it won't be re-delivered."""
        ...
