"""add tenant description column

Revision ID: 0002_tenant_description
Revises: 0001_initial
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_tenant_description"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "description")
