"""Per-turn mutable context passed to the conversation agent and its tools.

The tools mutate this object (recording cards, prices seen, handoff) rather than
returning rich objects, so the loop stays a simple string-in/string-out tool
protocol. Outgoing WhatsApp messages are enqueued through the injected
`enqueue_outgoing` callable — tools never touch the adapter directly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.retrieval.types import ProductHit
from app.runtime.types import ProductCard

EnqueueOutgoing = Callable[[dict], Awaitable[None]]


@dataclass
class TurnContext:
    tenant_id: str
    conversation_id: str | None = None
    channel: str = "whatsapp"  # "whatsapp" | "test_chat"
    lang: str = "en"

    # WhatsApp outgoing wiring — all None for the REST test-chat channel.
    green_api_instance_id: str | None = None
    chat_id: str | None = None
    enqueue_outgoing: EnqueueOutgoing | None = None

    # Populated during the turn by the tools:
    cards: list[ProductCard] = field(default_factory=list)
    tool_prices: set[float] = field(default_factory=set)
    hits_by_id: dict[str, ProductHit] = field(default_factory=dict)
    handoff: bool = False
    handoff_reason: str | None = None
