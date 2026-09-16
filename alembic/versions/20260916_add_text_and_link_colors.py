"""add text and link color customization columns to office_config

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f8
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("office_config", sa.Column("color_text_primary", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_text_secondary", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_link_primary", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_link_secondary", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("office_config", "color_link_secondary")
    op.drop_column("office_config", "color_link_primary")
    op.drop_column("office_config", "color_text_secondary")
    op.drop_column("office_config", "color_text_primary")
