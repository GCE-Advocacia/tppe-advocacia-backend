"""add email_attempts, email_provider_health, email_alert_log

Linha do tempo das tentativas, estado do circuit breaker por provedor,
controle de frequência dos alertas e referência do reenvio manual.

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
Create Date: 2026-10-28
"""

import sqlalchemy as sa

from alembic import op

revision = "2c3d4e5f6071"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_outbox",
        sa.Column(
            "resent_from_id",
            sa.String(36),
            sa.ForeignKey(
                "email_outbox.id",
                ondelete="SET NULL",
                name="fk_email_outbox_resent_from",
            ),
            nullable=True,
        ),
    )
    op.create_index("ix_email_outbox_created_at", "email_outbox", ["created_at"])

    op.create_table(
        "email_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "email_id",
            sa.String(36),
            sa.ForeignKey("email_outbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_attempts_email_id", "email_attempts", ["email_id"])
    op.create_index("ix_email_attempts_created_at", "email_attempts", ["created_at"])

    op.create_table(
        "email_provider_health",
        sa.Column("provider", sa.String(50), primary_key=True),
        sa.Column(
            "state",
            sa.Enum(
                "CLOSED",
                "OPEN",
                "HALF_OPEN",
                name="breakerstate",
                native_enum=False,
                length=10,
            ),
            nullable=False,
        ),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )

    op.create_table(
        "email_alert_log",
        sa.Column("kind", sa.String(50), primary_key=True),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_alert_log")
    op.drop_table("email_provider_health")
    op.drop_index("ix_email_attempts_created_at", table_name="email_attempts")
    op.drop_index("ix_email_attempts_email_id", table_name="email_attempts")
    op.drop_table("email_attempts")
    op.drop_index("ix_email_outbox_created_at", table_name="email_outbox")
    op.drop_constraint(
        "fk_email_outbox_resent_from", "email_outbox", type_="foreignkey"
    )
    op.drop_column("email_outbox", "resent_from_id")
