"""add recorrência em payments e email_outbox_id em payment_reminders

Vencimento recorrente (pedido do cliente em 27/10): os vencimentos criados
juntos compartilham recurrence_id e guardam a parcela. O lembrete passa a
apontar para o e-mail na fila.

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
Create Date: 2026-10-28
"""

import sqlalchemy as sa

from alembic import op

revision = "3d4e5f607182"
down_revision = "2c3d4e5f6071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("recurrence_id", sa.String(36), nullable=True))
    op.add_column("payments", sa.Column("installment", sa.Integer(), nullable=True))
    op.add_column("payments", sa.Column("installments", sa.Integer(), nullable=True))
    op.create_index("ix_payments_recurrence_id", "payments", ["recurrence_id"])

    op.add_column(
        "payment_reminders",
        sa.Column(
            "email_outbox_id",
            sa.String(36),
            sa.ForeignKey(
                "email_outbox.id",
                ondelete="SET NULL",
                name="fk_payment_reminders_email_outbox",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_payment_reminders_email_outbox_id",
        "payment_reminders",
        ["email_outbox_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_reminders_email_outbox_id", table_name="payment_reminders"
    )
    op.drop_constraint(
        "fk_payment_reminders_email_outbox", "payment_reminders", type_="foreignkey"
    )
    op.drop_column("payment_reminders", "email_outbox_id")
    op.drop_index("ix_payments_recurrence_id", table_name="payments")
    op.drop_column("payments", "installments")
    op.drop_column("payments", "installment")
    op.drop_column("payments", "recurrence_id")
