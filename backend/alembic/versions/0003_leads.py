"""add leads and lead_products tables with tenant-safe RLS

Revision ID: 0003_leads
Revises: 0002_tenant_description
Create Date: 2026-06-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_leads"
down_revision: Union[str, None] = "0002_tenant_description"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _id_col() -> sa.Column:
    return sa.Column(
        "id",
        sa.dialects.postgresql.UUID(as_uuid=False),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _tenant_col() -> sa.Column:
    return sa.Column(
        "tenant_id",
        sa.dialects.postgresql.UUID(as_uuid=False),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    pg = sa.dialects.postgresql

    op.create_table(
        "leads",
        _id_col(),
        _tenant_col(),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("did_buy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("business_name", sa.String(255)),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text()),
        sa.Column("last_message_sent_at", sa.DateTime(timezone=True)),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True)),
        sa.Column("last_conversation_summary", sa.Text()),
        sa.Column(
            "conversation_id",
            pg.UUID(as_uuid=False),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_timestamps(),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index(
        "uq_leads_tenant_phone_number", "leads", ["tenant_id", "phone_number"], unique=True
    )
    op.create_index("ix_leads_tenant_status", "leads", ["tenant_id", "status"])
    op.create_index(
        "ix_leads_tenant_last_message_sent_at",
        "leads",
        ["tenant_id", "last_message_sent_at"],
    )
    op.create_index("ix_leads_conversation_id", "leads", ["conversation_id"])

    op.create_table(
        "lead_products",
        _id_col(),
        sa.Column(
            "lead_id",
            pg.UUID(as_uuid=False),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            pg.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *_timestamps(),
    )
    op.create_index("ix_lead_products_lead_id", "lead_products", ["lead_id"])
    op.create_index("ix_lead_products_product_id", "lead_products", ["product_id"])
    op.create_index(
        "uq_lead_products_lead_product", "lead_products", ["lead_id", "product_id"], unique=True
    )

    op.execute("ALTER TABLE leads ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON leads USING "
        "(tenant_id IN (SELECT public.app_user_tenant_ids()))"
    )
    op.execute("ALTER TABLE lead_products ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON lead_products USING ("
        "EXISTS (SELECT 1 FROM leads l WHERE l.id = lead_products.lead_id "
        "AND l.tenant_id IN (SELECT public.app_user_tenant_ids()))"
        ")"
    )


def downgrade() -> None:
    op.drop_table("lead_products")
    op.drop_table("leads")
