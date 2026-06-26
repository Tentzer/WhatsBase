"""SQLAlchemy 2 ORM models — the database is the only interface between the
Builder agent (writes) and the Conversation agent (reads).

Every domain table carries `tenant_id` and is indexed on it: a missing tenant
filter is the worst bug in this product, so the column and its index exist on
day one. Embedding vectors use pgvector `halfvec(3072)` so the HNSW index is
buildable at the registry's native 3072 dimensions.

These models define columns and plain btree indexes. The specialized indexes
(HNSW on the vector, GIN on the metadata jsonb), the pgvector extension, the
halfvec version guard, and RLS policies are authored by hand in the initial
Alembic migration.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import EMBEDDING_DIM

UUID_PK = text("gen_random_uuid()")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def _pk() -> Mapped[str]:
    return mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=UUID_PK
    )


def _tenant_fk() -> Mapped[str]:
    return mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


# --------------------------------------------------------------------------- #
# Tenancy & auth
# --------------------------------------------------------------------------- #
class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Present in the deployed Supabase DB (added by Roy); mirror it here so the
    # onboarding endpoint can read/write tenant descriptions.
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    # Links to Supabase auth.users (managed by Supabase Auth, not by us).
    supabase_user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, unique=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)


# --------------------------------------------------------------------------- #
# WhatsApp + agent config (written by Builder, read by runtime)
# --------------------------------------------------------------------------- #
class WhatsAppInstance(TimestampMixin, Base):
    __tablename__ = "whatsapp_instances"

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    green_api_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Green API token, encrypted at rest (never logged). Encryption key in config.
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="disconnected")
    intake_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="polling")


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    system_prompt: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(String(64))
    language_policy: Mapped[str | None] = mapped_column(String(64))
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    escalation: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # building | live | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="building")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # catalog_sales (default) | lead_qualification
    agent_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="catalog_sales"
    )
    # Tenant controls for runtime behavior and lead automation.
    auto_reply_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    reengagement_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        # Idempotency: Builder upserts by (tenant_id, stable_key).
        Index("uq_products_tenant_stable_key", "tenant_id", "stable_key", unique=True),
    )

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    # Stable identity for idempotent re-builds (e.g. slug of owner-provided name).
    stable_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name_he: Mapped[str | None] = mapped_column(String(512))
    name_en: Mapped[str | None] = mapped_column(String(512))
    description_he: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(128))
    # colors, materials, style, ...
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ILS")
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # owner_input | builder_extracted
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="owner_input")

    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("uq_leads_tenant_phone_number", "tenant_id", "phone_number", unique=True),
        Index("ix_leads_tenant_status", "tenant_id", "status"),
        Index("ix_leads_tenant_last_message_sent_at", "tenant_id", "last_message_sent_at"),
    )

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    # pending | contacted | qualified | not_interested | success | awaiting_owner
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    did_buy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    business_name: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    notes: Mapped[str | None] = mapped_column(Text)
    last_message_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_conversation_summary: Mapped[str | None] = mapped_column(Text)
    last_reengagement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reengagement_decision: Mapped[str | None] = mapped_column(String(32))
    reengagement_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    reengagement_cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    conversation_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
    )

    interested_products: Mapped[list[LeadProduct]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class LeadProduct(TimestampMixin, Base):
    __tablename__ = "lead_products"
    __table_args__ = (
        Index("uq_lead_products_lead_product", "lead_id", "product_id", unique=True),
    )

    id: Mapped[str] = _pk()
    lead_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    lead: Mapped[Lead] = relationship(back_populates="interested_products")
    product: Mapped[Product] = relationship()


class LeadAutomationEvent(TimestampMixin, Base):
    __tablename__ = "lead_automation_events"
    __table_args__ = (
        Index(
            "ix_lead_automation_events_tenant_lead_created",
            "tenant_id",
            "lead_id",
            "created_at",
        ),
        Index(
            "uq_lead_automation_events_idempotency_key",
            "idempotency_key",
            unique=True,
        ),
    )

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    lead_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    automation_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="reengagement"
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ProductImage(TimestampMixin, Base):
    __tablename__ = "product_images"

    id: Mapped[str] = _pk()
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text)
    caption_he: Mapped[str | None] = mapped_column(Text)
    caption_en: Mapped[str | None] = mapped_column(Text)

    product: Mapped[Product] = relationship(back_populates="images")


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #
class Embedding(TimestampMixin, Base):
    __tablename__ = "embeddings"

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    # product | business_info
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector: Mapped[list[float]] = mapped_column(HALFVEC(EMBEDDING_DIM), nullable=False)
    # Hybrid-filter payload: category, colors, price, in_stock, ... (GIN-indexed).
    embedding_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # staging | active — supports atomic stage->swap on rebuild (invariant #5).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class BusinessInfo(TimestampMixin, Base):
    __tablename__ = "business_info"

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    # hours | location | policy | faq | other
    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    content_he: Mapped[str | None] = mapped_column(Text)
    content_en: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- #
# Conversations (written by runtime only)
# --------------------------------------------------------------------------- #
class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_tenant_phone", "tenant_id", "customer_phone"),
    )

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = _pk()
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # inbound | outbound
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    # text | image
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    content: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    # Langfuse trace id for this turn (debugging entry point).
    agent_trace_id: Mapped[str | None] = mapped_column(String(128))

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


# --------------------------------------------------------------------------- #
# Build runs (Builder agent audit log)
# --------------------------------------------------------------------------- #
class BuildRun(TimestampMixin, Base):
    __tablename__ = "build_runs"

    id: Mapped[str] = _pk()
    tenant_id: Mapped[str] = _tenant_fk()
    # running | passed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    input_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    report: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
