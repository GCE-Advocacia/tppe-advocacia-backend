"""add email_outbox

Fila de saída e histórico de e-mails. O convite de usuário passa a ser
gravado aqui na mesma transação e enviado pelo worker do scheduler.

Revision ID: 1b2c3d4e5f60
Revises: 0a9b8c7d6e5f
Create Date: 2026-10-28
"""

import sqlalchemy as sa

from alembic import op

revision = "1b2c3d4e5f60"
down_revision = "0a9b8c7d6e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(100), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("to", sa.JSON(), nullable=False),
        sa.Column("cc", sa.JSON(), nullable=False),
        sa.Column("bcc", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SENDING",
                "SENT",
                "FAILED",
                "DEAD",
                "CANCELLED",
                name="emailstatus",
                native_enum=False,
                length=10,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True),
        sa.Column("related_type", sa.String(50), nullable=True),
        sa.Column("related_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_email_outbox_status_next_attempt",
        "email_outbox",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_email_outbox_related", "email_outbox", ["related_type", "related_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_outbox_related", table_name="email_outbox")
    op.drop_index("ix_email_outbox_status_next_attempt", table_name="email_outbox")
    op.drop_table("email_outbox")
