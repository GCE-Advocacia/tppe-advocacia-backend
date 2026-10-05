"""add button hover and text color customization columns to office_config

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("office_config", sa.Column("color_buttons_hover", sa.String(50), nullable=True))
    op.add_column("office_config", sa.Column("color_buttons_text", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("office_config", "color_buttons_text")
    op.drop_column("office_config", "color_buttons_hover")
