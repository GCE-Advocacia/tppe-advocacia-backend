"""add sync_token to google_credential

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b2c3
Create Date: 2026-07-01
"""

import sqlalchemy as sa

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "google_credential", sa.Column("sync_token", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("google_credential", "sync_token")
