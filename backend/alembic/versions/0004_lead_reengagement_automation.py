"""add lead reengagement fields and automation events table

Revision ID: 0004_lead_reengagement_automation
Revises: 0003_leads
Create Date: 2026-06-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_lead_reengagement_automation"
down_revision: Union[str, None] = "0003_leads"
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

    op.add_column("leads", sa.Column("last_reengagement_at", sa.DateTime(timezone=True)))
    op.add_column("leads", sa.Column("last_reengagement_decision", sa.String(length=32)))
    op.add_column(
        "leads",
        sa.Column(
            "reengagement_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "leads", sa.Column("reengagement_cooldown_until", sa.DateTime(timezone=True))
    )

    op.create_table(
        "lead_automation_events",
        _id_col(),
        _tenant_col(),
        sa.Column(
            "lead_id",
            pg.UUID(as_uuid=False),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "automation_type",
            sa.String(64),
            nullable=False,
            server_default="reengagement",
        ),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("scheduled_for", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "payload_json",
            pg.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_lead_automation_events_tenant_id", "lead_automation_events", ["tenant_id"]
    )
    op.create_index(
        "ix_lead_automation_events_lead_id", "lead_automation_events", ["lead_id"]
    )
    op.create_index(
        "ix_lead_automation_events_tenant_lead_created",
        "lead_automation_events",
        ["tenant_id", "lead_id", "created_at"],
    )
    op.create_index(
        "uq_lead_automation_events_idempotency_key",
        "lead_automation_events",
        ["idempotency_key"],
        unique=True,
    )

    op.execute("ALTER TABLE lead_automation_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON lead_automation_events USING "
        "(tenant_id IN (SELECT public.app_user_tenant_ids()))"
    )


def downgrade() -> None:
    op.drop_table("lead_automation_events")
    op.drop_column("leads", "reengagement_cooldown_until")
    op.drop_column("leads", "reengagement_attempt_count")
    op.drop_column("leads", "last_reengagement_decision")
    op.drop_column("leads", "last_reengagement_at")
