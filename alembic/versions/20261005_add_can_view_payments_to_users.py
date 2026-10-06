"""add can_view_payments to users

Permissao para usuarios com papel USER visualizarem os vencimentos
(pagamentos). Usuarios existentes e novos comecam sem acesso (false).

Revision ID: 587e82a35097
Revises: b1c2d3e4f5a6
Create Date: 2026-10-05
"""

import sqlalchemy as sa

from alembic import op

revision = "587e82a35097"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_view_payments",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "can_view_payments")
