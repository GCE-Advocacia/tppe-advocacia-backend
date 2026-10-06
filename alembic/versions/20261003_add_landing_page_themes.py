"""add landing_page_themes table and default themes

Revision ID: e4f5a6b7c8d9
Revises: e0f1a2b3c4d5
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None

DEFAULT_THEMES = [
    {
        "name": "Clássico Navy & Wine (Padrão)",
        "description": "Combinação tradicional com azul marinho institucional e detalhes em bordô elegante.",
        "is_predefined": True,
        "color": "#232C43",
        "color_bg_primary": "#232C43",
        "color_bg_secondary": "#F5F3EF",
        "color_bg_sobre": "#FFFFFF",
        "color_buttons": "#661C16",
        "color_buttons_hover": "#A52020",
        "color_buttons_text": "#FFFFFF",
        "color_title_primary": "#FFFFFF",
        "color_title_secondary": "#232C43",
        "color_text_primary": "#FFFFFF",
        "color_text_secondary": "#6B7280",
        "color_link_primary": "#FFFFFF",
        "color_link_secondary": "#661C16",
    },
    {
        "name": "Dourado & Ônix Nobre",
        "description": "Estilo executivo premium com preto ônix profundo e detalhes sofisticados em ouro envelhecido.",
        "is_predefined": True,
        "color": "#12161A",
        "color_bg_primary": "#12161A",
        "color_bg_secondary": "#F9F9F8",
        "color_bg_sobre": "#FFFFFF",
        "color_buttons": "#C5A059",
        "color_buttons_hover": "#A38038",
        "color_buttons_text": "#12161A",
        "color_title_primary": "#C5A059",
        "color_title_secondary": "#12161A",
        "color_text_primary": "#E5E7EB",
        "color_text_secondary": "#4B5563",
        "color_link_primary": "#C5A059",
        "color_link_secondary": "#99752A",
    },
    {
        "name": "Esmeralda & Âmbar Corporativo",
        "description": "Identidade corporativa distinta com verde floresta sóbrio e acentos em cobre/âmbar.",
        "is_predefined": True,
        "color": "#1B3B36",
        "color_bg_primary": "#1B3B36",
        "color_bg_secondary": "#F4F6F5",
        "color_bg_sobre": "#FFFFFF",
        "color_buttons": "#D97706",
        "color_buttons_hover": "#B45309",
        "color_buttons_text": "#FFFFFF",
        "color_title_primary": "#FFFFFF",
        "color_title_secondary": "#1B3B36",
        "color_text_primary": "#D1D5DB",
        "color_text_secondary": "#4B5563",
        "color_link_primary": "#FDE68A",
        "color_link_secondary": "#B45309",
    },
]


def upgrade() -> None:
    themes_table = op.create_table(
        "landing_page_themes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_predefined", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=False),
        sa.Column("color_bg_primary", sa.String(length=50), nullable=False),
        sa.Column("color_bg_secondary", sa.String(length=50), nullable=False),
        sa.Column("color_bg_sobre", sa.String(length=50), nullable=False),
        sa.Column("color_buttons", sa.String(length=50), nullable=False),
        sa.Column("color_buttons_hover", sa.String(length=50), nullable=False),
        sa.Column("color_buttons_text", sa.String(length=50), nullable=False),
        sa.Column("color_title_primary", sa.String(length=50), nullable=False),
        sa.Column("color_title_secondary", sa.String(length=50), nullable=False),
        sa.Column("color_text_primary", sa.String(length=50), nullable=False),
        sa.Column("color_text_secondary", sa.String(length=50), nullable=False),
        sa.Column("color_link_primary", sa.String(length=50), nullable=False),
        sa.Column("color_link_secondary", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_landing_page_themes_id"), "landing_page_themes", ["id"], unique=False)

    op.bulk_insert(themes_table, DEFAULT_THEMES)


def downgrade() -> None:
    op.drop_index(op.f("ix_landing_page_themes_id"), table_name="landing_page_themes")
    op.drop_table("landing_page_themes")
