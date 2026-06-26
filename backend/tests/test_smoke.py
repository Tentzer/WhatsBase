"""M1 smoke test: settings load, the model registry is correct, and all ORM
models register on the metadata. No live cloud credentials required.
"""

from __future__ import annotations

from app.core import schema  # noqa: F401 - registers models on Base.metadata
from app.core.config import Settings, get_settings
from app.core.db import Base
from app.core.models import EMBEDDING_DIM, get_model

EXPECTED_TABLES = {
    "tenants",
    "users",
    "whatsapp_instances",
    "agents",
    "products",
    "leads",
    "lead_products",
    "lead_automation_events",
    "product_images",
    "embeddings",
    "business_info",
    "conversations",
    "messages",
    "build_runs",
}


def test_settings_load_without_env():
    # All fields have defaults, so Settings() must construct with no .env present.
    settings = Settings()
    assert settings.intake_mode in ("polling", "webhook")
    assert get_settings() is get_settings()  # cached singleton


def test_model_registry():
    assert get_model("conversation").provider == "anthropic"
    assert get_model("conversation").name == "claude-sonnet-4-6"
    assert get_model("vision").provider == "openai"
    assert get_model("vision").name == "gpt-4o-mini"
    emb = get_model("embedding")
    assert emb.provider == "openai"
    assert emb.name == "text-embedding-3-large"
    assert emb.dimensions == 3072
    assert EMBEDDING_DIM == 3072


def test_all_tables_registered():
    assert EXPECTED_TABLES <= set(Base.metadata.tables.keys())


def test_every_domain_table_has_tenant_id():
    # Tenant isolation is the core invariant — every domain table (except the
    # child tables isolated via their parent) must carry tenant_id.
    child_tables = {"product_images", "messages", "lead_products", "tenants"}
    for name, table in Base.metadata.tables.items():
        if name in child_tables:
            continue
        assert "tenant_id" in table.columns, f"{name} is missing tenant_id"
