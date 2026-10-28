"""add email_profiles e detalhes na auditoria

Perfis de envio de e-mail configurados pela tela (primário e reserva), com a
senha criptografada. Já cria os dois perfis, desativados: enquanto nenhum for
ativado, o envio segue pelas variáveis SMTP_* do .env.

Na auditoria: ação EMAIL_SETTINGS_UPDATED e coluna ``details`` (JSON) para o
diff dos campos alterados.

Revision ID: 9f1e2d3c4b5a
Revises: c1d2e3f4a5b6
Create Date: 2026-10-28
"""

import sqlalchemy as sa

from alembic import op

revision = "9f1e2d3c4b5a"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, unique=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("security", sa.String(20), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("reply_to", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_email_profiles_id", "email_profiles", ["id"])

    profiles = sa.table(
        "email_profiles",
        sa.column("name", sa.String),
        sa.column("priority", sa.Integer),
        sa.column("provider", sa.String),
        sa.column("port", sa.Integer),
        sa.column("security", sa.String),
    )
    defaults = {"provider": "smtp", "port": 587, "security": "starttls"}
    op.bulk_insert(
        profiles,
        [
            {"name": "Primário", "priority": 1, **defaults},
            {"name": "Reserva", "priority": 2, **defaults},
        ],
    )

    op.execute(
        "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'EMAIL_SETTINGS_UPDATED'"
    )
    op.add_column("audit_logs", sa.Column("details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "details")
    # O valor EMAIL_SETTINGS_UPDATED fica no enum: o PostgreSQL não remove
    # valores sem recriar o tipo (mesmo caso de USER_UPDATED).
    op.drop_index("ix_email_profiles_id", table_name="email_profiles")
    op.drop_table("email_profiles")
