"""add agent_type column to agents

Revision ID: 0006_agent_type
Revises: 0005_agent_controls
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_agent_type"
down_revision: Union[str, None] = "0005_agent_controls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "agent_type",
            sa.String(32),
            nullable=False,
            server_default="catalog_sales",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "agent_type")
