"""add color to office_config

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-09-12
"""

import sqlalchemy as sa

from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "office_config", sa.Column("color", sa.String(50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("office_config", "color")
