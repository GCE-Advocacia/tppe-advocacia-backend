"""Persist administrator-defined defaults for each branding asset.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
"""

import sqlalchemy as sa

from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None
FIELDS = (
    "default_logo_url",
    "default_logo_dark_url",
    "default_system_logo_url",
    "default_system_logo_dark_url",
    "default_favicon_url",
)


def upgrade() -> None:
    for name in FIELDS:
        op.add_column("office_config", sa.Column(name, sa.String(500), nullable=True))


def downgrade() -> None:
    for name in FIELDS:
        op.drop_column("office_config", name)
