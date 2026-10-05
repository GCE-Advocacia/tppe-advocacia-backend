"""add financial_transactions table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-13
"""

import sqlalchemy as sa

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "INCOME",
                "EXPENSE",
                name="transactiontype",
                native_enum=False,
                length=10,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_financial_transactions_created_by",
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_financial_transactions_id"),
        "financial_transactions",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_transaction_date",
        "financial_transactions",
        ["transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_type",
        "financial_transactions",
        ["type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_financial_transactions_type", table_name="financial_transactions")
    op.drop_index(
        "ix_financial_transactions_transaction_date",
        table_name="financial_transactions",
    )
    op.drop_index(
        op.f("ix_financial_transactions_id"), table_name="financial_transactions"
    )
    op.drop_table("financial_transactions")
