"""add theme_id to office_config

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("office_config", sa.Column("theme_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_office_config_theme_id",
        "office_config",
        "landing_page_themes",
        ["theme_id"],
        ["id"],
        ondelete="SET NULL",
    )
    bind = op.get_bind()
    theme_id = bind.execute(
        sa.text(
            "SELECT id FROM landing_page_themes "
            "WHERE is_predefined IS TRUE "
            "ORDER BY id ASC LIMIT 1"
        )
    ).scalar()
    if theme_id:
        bind.execute(
            sa.text("UPDATE office_config SET theme_id = :theme_id WHERE theme_id IS NULL"),
            {"theme_id": theme_id},
        )


def downgrade() -> None:
    op.drop_constraint("fk_office_config_theme_id", "office_config", type_="foreignkey")
    op.drop_column("office_config", "theme_id")
