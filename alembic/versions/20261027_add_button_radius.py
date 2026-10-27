"""Persist the action button radius.

Revision ID: 7d8e9f0a1b2c
Revises: c1d2e3f4a5b6
"""

import sqlalchemy as sa

from alembic import op

revision = "7d8e9f0a1b2c"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "office_config",
        sa.Column("button_radius", sa.String(20), nullable=False, server_default="6px"),
    )


def downgrade() -> None:
    op.drop_column("office_config", "button_radius")
