"""add payments

Revision ID: 44d4da2b8fa6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-11 19:54:43.856682+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '44d4da2b8fa6'

down_revision: Union[str, None] = 'e5f6a7b8c9d0'

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name="fk_payments_client_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_payments_created_by",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_payments_id",
        "payments",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_payments_client_id",
        "payments",
        ["client_id"],
        unique=False,
    )

    op.create_index(
        "ix_payments_payment_date",
        "payments",
        ["payment_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payments_payment_date",
        table_name="payments",
    )

    op.drop_index(
        "ix_payments_client_id",
        table_name="payments",
    )

    op.drop_index(
        "ix_payments_id",
        table_name="payments",
    )

    op.drop_table("payments")