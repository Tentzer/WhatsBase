"""Conversation-agent tool schemas + dispatch.

Schemas are the native Anthropic tool definitions handed to the Messages API.
Descriptions are short and behavioral. Every tool takes `tenant_id` implicitly
through the `TurnContext`, never as a model-supplied argument.
"""

from __future__ import annotations

from app.runtime.context import TurnContext
from app.runtime.tools import business_info, handoff, product_cards, search_products

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_products",
        "description": (
            "Search this business's product catalog. Returns matching products "
            "with id, name, price, stock status, and category. Use the optional "
            "filters to narrow by category, price range, or stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What the customer is looking for, in their words.",
                },
                "category": {"type": "string"},
                "in_stock": {"type": "boolean"},
                "price_min": {"type": "number"},
                "price_max": {"type": "number"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_business_info",
        "description": (
            "Get this business's information — hours, location, policy, or faq. "
            "Use for questions about opening hours, address, returns, or shipping."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": ["hours", "location", "policy", "faq", "other"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "send_product_cards",
        "description": (
            "Show the customer specific products as cards (photo, name, price). "
            "Pass product ids returned by search_products. Call this whenever you "
            "present products so the customer sees the photos and prices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["product_ids"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": (
            "Escalate to a human. Use when the customer is angry, explicitly asks "
            "for a person, or asks something you cannot answer from the catalog or "
            "business info."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]

_HANDLERS = {
    "search_products": search_products.run,
    "get_business_info": business_info.run,
    "send_product_cards": product_cards.run,
    "handoff_to_human": handoff.run,
}


async def dispatch(name: str, tool_input: dict, ctx: TurnContext) -> str:
    """Run a tool by name and return its string result (the tool_result block)."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    return await handler(ctx, **(tool_input or {}))
