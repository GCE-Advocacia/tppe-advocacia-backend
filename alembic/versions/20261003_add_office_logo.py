"""add persisted office logo

Revision ID: a7b8c9d0e1f2
Revises: b1c2d3e4f5a6
Create Date: 2026-10-03
"""

import sqlalchemy as sa

from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("office_config", sa.Column("logo_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("office_config", "logo_url")
