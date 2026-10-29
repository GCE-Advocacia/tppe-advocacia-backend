"""Add light/dark, system and favicon assets; retire background removal.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""

import sqlalchemy as sa

from alembic import op

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep logo_url so an existing published logo remains the shared default.
    for name in (
        "logo_dark_url",
        "system_logo_url",
        "system_logo_dark_url",
        "favicon_url",
    ):
        op.add_column("office_config", sa.Column(name, sa.String(500), nullable=True))
    for name in (
        "logo_same_for_themes",
        "system_logo_same_for_themes",
        "system_uses_landing_logo",
    ):
        op.add_column(
            "office_config",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    for name in (
        "logo_original_url",
        "logo_remove_background",
        "logo_background_tolerance",
    ):
        op.drop_column("office_config", name)


def downgrade() -> None:
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
    for name in (
        "logo_dark_url",
        "system_logo_url",
        "system_logo_dark_url",
        "favicon_url",
        "logo_same_for_themes",
        "system_logo_same_for_themes",
        "system_uses_landing_logo",
    ):
        op.drop_column("office_config", name)
