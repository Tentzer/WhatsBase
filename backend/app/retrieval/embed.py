from __future__ import annotations

import asyncio
from functools import lru_cache

from app.core.config import get_settings
from app.core.models import get_model


@lru_cache(maxsize=1)
def _get_openai():
    from langfuse.openai import OpenAI  # drop-in: auto-tracks model/tokens as Langfuse generation

    return OpenAI(api_key=get_settings().openai_api_key)


async def embed_query(text: str) -> list[float]:
    """Embed a query string using the embedding registry model."""
    model_cfg = get_model("embedding")
    client = _get_openai()

    def _call() -> list[float]:
        response = client.embeddings.create(
            model=model_cfg.name,
            input=text,
            dimensions=model_cfg.dimensions,
        )
        return response.data[0].embedding

    return await asyncio.to_thread(_call)
