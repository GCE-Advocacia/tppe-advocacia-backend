"""add email_identity e preset do perfil (US25)

Identidade (nome do remetente e responder para) separada da conta: vale
também para a conta do sistema. O perfil reserva deixa de ser usado (a
reserva passa a ser sempre o SMTP do .env) e o Resend sai da tela.

Dados mantidos: se só o antigo reserva estava ativo e era SMTP, ele vira a
conta própria; perfis Resend ficam salvos, mas desativados.

Revision ID: 4e5f60718293
Revises: 3d4e5f607182
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "4e5f60718293"
down_revision = "3d4e5f607182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_profiles", sa.Column("preset", sa.String(30), nullable=True))

    op.create_table(
        "email_identity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("reply_to", sa.String(255), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
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

    bind = op.get_bind()
    profiles = {
        row.priority: row
        for row in bind.execute(
            sa.text(
                "SELECT id, priority, provider, is_active, from_name, reply_to "
                "FROM email_profiles"
            )
        )
    }
    primary, fallback = profiles.get(1), profiles.get(2)

    # Só o reserva estava em uso: troca as prioridades para ele virar a conta própria.
    if (
        primary is not None
        and fallback is not None
        and not primary.is_active
        and fallback.is_active
        and fallback.provider == "smtp"
    ):
        bind.execute(
            sa.text("UPDATE email_profiles SET priority = 3 WHERE id = :id"),
            {"id": primary.id},
        )
        bind.execute(
            sa.text("UPDATE email_profiles SET priority = 1 WHERE id = :id"),
            {"id": fallback.id},
        )
        bind.execute(
            sa.text("UPDATE email_profiles SET priority = 2 WHERE id = :id"),
            {"id": primary.id},
        )
        primary, fallback = fallback, primary

    source = (
        primary
        if primary is not None and (primary.from_name or primary.reply_to)
        else fallback
    )
    op.bulk_insert(
        sa.table(
            "email_identity",
            sa.column("id", sa.Integer),
            sa.column("from_name", sa.String),
            sa.column("reply_to", sa.String),
        ),
        [
            {
                "id": 1,
                "from_name": source.from_name if source is not None else None,
                "reply_to": source.reply_to if source is not None else None,
            }
        ],
    )

    bind.execute(
        sa.text(
            "UPDATE email_profiles SET is_active = false, version = version + 1 "
            "WHERE priority <> 1 OR provider <> 'smtp'"
        )
    )
    bind.execute(
        sa.text("UPDATE email_profiles SET preset = 'other' WHERE host IS NOT NULL")
    )


def downgrade() -> None:
    op.drop_table("email_identity")
    op.drop_column("email_profiles", "preset")
