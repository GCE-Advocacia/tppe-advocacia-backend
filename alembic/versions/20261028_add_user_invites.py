"""add user_invites e status do usuário

Convite por link de uso único no lugar da senha temporária por e-mail.
Usuário novo nasce INVITED e sem senha (hashed_password passa a aceitar
nulo); os já existentes ficam ACTIVE.

Revision ID: 0a9b8c7d6e5f
Revises: 9f1e2d3c4b5a
Create Date: 2026-10-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0a9b8c7d6e5f"
down_revision = "9f1e2d3c4b5a"
branch_labels = None
depends_on = None

user_status = sa.Enum("INVITED", "ACTIVE", name="userstatus")


def upgrade() -> None:
    user_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column("status", user_status, nullable=False, server_default="ACTIVE"),
    )
    op.alter_column(
        "users", "hashed_password", existing_type=sa.String(255), nullable=True
    )

    op.create_table(
        "user_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_user_invites_id", "user_invites", ["id"])
    op.create_index("ix_user_invites_user_id", "user_invites", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_invites_user_id", table_name="user_invites")
    op.drop_index("ix_user_invites_id", table_name="user_invites")
    op.drop_table("user_invites")
    # Convidados que nunca aceitaram não têm senha: marca com um valor que não
    # é hash válido (ninguém entra com ele) para o NOT NULL voltar sem apagar
    # usuários. Depois do downgrade, use a redefinição de senha para eles.
    op.execute("UPDATE users SET hashed_password = '!' WHERE hashed_password IS NULL")
    op.alter_column(
        "users", "hashed_password", existing_type=sa.String(255), nullable=False
    )
    op.drop_column("users", "status")
    user_status.drop(op.get_bind(), checkfirst=True)
