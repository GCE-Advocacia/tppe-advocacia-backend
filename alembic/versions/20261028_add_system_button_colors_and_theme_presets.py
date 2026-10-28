"""add system button color columns to office_config and landing_page_themes

Revision ID: 9f0a1b2c3d4e
Revises: 8e9f0a1b2c3d
Create Date: 2026-10-28
"""

import sqlalchemy as sa

from alembic import op

revision = "9f0a1b2c3d4e"
down_revision = "8e9f0a1b2c3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "office_config",
        sa.Column(
            "system_uses_landing_buttons",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "office_config",
        sa.Column("color_buttons_system", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "office_config",
        sa.Column("color_buttons_system_hover", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "office_config",
        sa.Column("color_buttons_system_text", sa.String(length=50), nullable=True),
    )

    op.add_column(
        "landing_page_themes",
        sa.Column(
            "system_uses_landing_buttons",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "landing_page_themes",
        sa.Column("color_buttons_system", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "landing_page_themes",
        sa.Column("color_buttons_system_hover", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "landing_page_themes",
        sa.Column("color_buttons_system_text", sa.String(length=50), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE landing_page_themes
            SET system_uses_landing_buttons = FALSE,
                color_buttons_system = '#111827',
                color_buttons_system_hover = '#1F2937',
                color_buttons_system_text = '#FFFFFF'
            WHERE name LIKE 'Clássico Navy & Wine%'
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE landing_page_themes
            SET system_uses_landing_buttons = TRUE,
                color_buttons_system = color_buttons,
                color_buttons_system_hover = color_buttons_hover,
                color_buttons_system_text = color_buttons_text
            WHERE name NOT LIKE 'Clássico Navy & Wine%'
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE office_config
            SET system_uses_landing_buttons = FALSE,
                color_buttons_system = '#111827',
                color_buttons_system_hover = '#1F2937',
                color_buttons_system_text = '#FFFFFF'
            WHERE (color_buttons_system IS NULL OR color_buttons_system = '#661C16')
              AND (theme_id IS NULL OR theme_id IN (
                  SELECT id FROM landing_page_themes WHERE name LIKE 'Clássico Navy & Wine%'
              ))
            """
        )
    )


def downgrade() -> None:
    op.drop_column("landing_page_themes", "color_buttons_system_text")
    op.drop_column("landing_page_themes", "color_buttons_system_hover")
    op.drop_column("landing_page_themes", "color_buttons_system")
    op.drop_column("landing_page_themes", "system_uses_landing_buttons")

    op.drop_column("office_config", "color_buttons_system_text")
    op.drop_column("office_config", "color_buttons_system_hover")
    op.drop_column("office_config", "color_buttons_system")
    op.drop_column("office_config", "system_uses_landing_buttons")
