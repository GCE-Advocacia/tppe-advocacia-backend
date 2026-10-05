"""add payments.status and payment_reminders table (US02)

Revision ID: a9b8c7d6e5f4
Revises: b1c2d3e4f5a6
Create Date: 2026-10-04
"""

import sqlalchemy as sa

from alembic import op

revision = "a9b8c7d6e5f4"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PAID",
                name="paymentstatus",
                native_enum=False,
                length=10,
            ),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_payments_status",
        "payments",
        ["status"],
        unique=False,
    )

    op.create_table(
        "payment_reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "D_MINUS_1",
                "D_ZERO",
                name="reminderkind",
                native_enum=False,
                length=10,
            ),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "SENT",
                "FAILED",
                "NO_EMAIL",
                name="reminderstatus",
                native_enum=False,
                length=10,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name="fk_payment_reminders_payment_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "payment_id", "kind", name="uq_payment_reminders_payment_kind"
        ),
    )
    op.create_index(
        "ix_payment_reminders_id",
        "payment_reminders",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_reminders_payment_id",
        "payment_reminders",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_reminders_status",
        "payment_reminders",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_payment_reminders_sent_at",
        "payment_reminders",
        ["sent_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_payment_reminders_sent_at", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_status", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_payment_id", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_id", table_name="payment_reminders")
    op.drop_table("payment_reminders")

    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_column("payments", "status")
