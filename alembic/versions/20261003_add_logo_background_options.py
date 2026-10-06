"""Preserve logo source and optional background removal settings.

Revision ID: c8d9e0f1a2b3
Revises: a7b8c9d0e1f2
"""

import sqlalchemy as sa

from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "office_config", sa.Column("logo_original_url", sa.String(500), nullable=True)
    )
    op.add_column(
        "office_config",
        sa.Column(
            "logo_remove_background",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "office_config",
        sa.Column(
            "logo_background_tolerance",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )


def downgrade() -> None:
    op.drop_column("office_config", "logo_background_tolerance")
    op.drop_column("office_config", "logo_remove_background")
    op.drop_column("office_config", "logo_original_url")
