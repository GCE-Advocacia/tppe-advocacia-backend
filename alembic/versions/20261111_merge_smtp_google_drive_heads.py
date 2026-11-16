"""merge heads do e-mail (SMTP) e do Google Drive

As duas features saíram de pontos diferentes da main e cada uma aplicou a sua
DDL. Esta revisao apenas une as pontas.

Revision ID: 5f6071829304
Revises: 4e5f60718293, 8e9f0a1b2c3d
Create Date: 2026-11-11
"""

revision = "5f6071829304"
down_revision = ("4e5f60718293", "8e9f0a1b2c3d")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
