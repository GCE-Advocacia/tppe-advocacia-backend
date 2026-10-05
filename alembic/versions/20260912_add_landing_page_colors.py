"""add landing page color customization columns to office_config

Revision ID: a1b2c3d4e5f8
Revises: f7a8b9c0d1e2
Create Date: 2026-09-12
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f8"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("office_config", sa.Column("color_bg_primary", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_bg_secondary", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_bg_sobre", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_buttons", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_title_primary", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_title_secondary", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("office_config", "color_title_secondary")
    op.drop_column("office_config", "color_title_primary")
    op.drop_column("office_config", "color_buttons")
    op.drop_column("office_config", "color_bg_sobre")
    op.drop_column("office_config", "color_bg_secondary")
    op.drop_column("office_config", "color_bg_primary")
