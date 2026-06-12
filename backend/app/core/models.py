"""Model registry — the ONE place model selections live (SPEC invariant).

Every LLM/embedding call in the codebase must read its provider + model name +
params from here. Swapping any model is a one-line change in this file and
nowhere else. Do not hardcode a model name anywhere outside this module.

Roles:
  BUILDER      — builder reasoning loop (Anthropic, tool-calling)
  CONVERSATION — runtime conversation agent (Anthropic, native tool use)
  VISION       — builder image captioning (OpenAI, structured JSON output)
  EMBEDDING    — knowledge-base embeddings (OpenAI, multilingual He+En)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Provider = Literal["anthropic", "openai"]
Role = Literal["builder", "conversation", "vision", "embedding"]


@dataclass(frozen=True)
class ModelConfig:
    role: Role
    provider: Provider
    name: str
    # Generation params (ignored by embedding role).
    max_tokens: int | None = None
    temperature: float | None = None
    # Embedding dimensionality (None for non-embedding roles).
    # NOTE: text-embedding-3-large native dim is 3072. We keep it native and
    # store vectors as pgvector `halfvec(3072)` so an HNSW index is buildable
    # (the `vector` type caps HNSW at 2000 dims; `halfvec` allows up to 4000).
    dimensions: int | None = None
    extra: dict = field(default_factory=dict)


BUILDER = ModelConfig(
    role="builder",
    provider="anthropic",
    name="claude-sonnet-4-6",
    max_tokens=4096,
    temperature=0.2,
)

CONVERSATION = ModelConfig(
    role="conversation",
    provider="anthropic",
    name="claude-sonnet-4-6",
    max_tokens=2048,
    temperature=0.3,
)

VISION = ModelConfig(
    role="vision",
    provider="openai",
    name="gpt-4o-mini",
    max_tokens=1024,
    temperature=0.0,
)

EMBEDDING = ModelConfig(
    role="embedding",
    provider="openai",
    name="text-embedding-3-large",
    dimensions=3072,
)

REGISTRY: dict[Role, ModelConfig] = {
    "builder": BUILDER,
    "conversation": CONVERSATION,
    "vision": VISION,
    "embedding": EMBEDDING,
}


def get_model(role: Role) -> ModelConfig:
    """Look up the configured model for a role."""
    return REGISTRY[role]


# Convenience: the embedding dimension is referenced by the schema/migration
# and retrieval. Centralized here so it can never drift from the model choice.
EMBEDDING_DIM: int = EMBEDDING.dimensions or 0
