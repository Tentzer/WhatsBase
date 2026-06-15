"""add agent control toggles for auto-reply and re-engagement

Revision ID: 0005_agent_controls
Revises: 0004_lead_reengagement_automation
Create Date: 2026-06-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_agent_controls"
down_revision: Union[str, None] = "0004_lead_reengagement_automation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "auto_reply_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "reengagement_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "reengagement_enabled")
    op.drop_column("agents", "auto_reply_enabled")
