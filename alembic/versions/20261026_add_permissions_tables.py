"""add permissions tables

Substitui a coluna users.can_view_payments por permissoes por aba:
- permissions: catalogo das abas da area do sistema (uma linha por aba);
- user_permissions: abas liberadas para cada usuario.

Migracao de dados sem perda de acesso: todo USER existente recebe as abas
que ja acessava (artigos, clientes, agenda, processos, tarefas,
notificacoes) e quem tinha can_view_payments = true recebe tambem
pagamentos. O downgrade recria a coluna a partir de pagamentos.

Revision ID: d7e8f9a0b1c2
Revises: c1d2e3f4a5b6
Create Date: 2026-10-26
"""

import sqlalchemy as sa

from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("landing_page", "Landing Page", "Editar a landing page, temas e logos"),
    ("artigos", "Artigos", "Criar, editar e publicar artigos"),
    ("leads", "Leads", "Ver e atribuir os leads do site"),
    ("clientes", "Clientes", "Cadastrar e editar clientes, notas e linha do tempo"),
    ("agenda", "Agenda", "Compromissos e integração com o Google Agenda"),
    ("pagamentos", "Pagamentos", "Vencimentos dos clientes e lembretes"),
    ("processos", "Processos", "Processos, movimentações, documentos e prazos"),
    ("tarefas", "Tarefas", "Quadro de tarefas"),
    ("notificacoes", "Notificações", "Preferências de notificação"),
    ("logs_api", "Logs DataJud", "Logs de chamadas a APIs externas e sincronização"),
    ("feriados", "Feriados", "Cadastro de feriados forenses"),
    ("financeiro", "Financeiro", "Entradas, saídas e resumo financeiro"),
]

# Abas que todo USER ja acessava antes desta migration.
LEGACY_USER_KEYS = (
    "artigos",
    "clientes",
    "agenda",
    "processos",
    "tarefas",
    "notificacoes",
)


def upgrade() -> None:
    permissions = op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_permissions_id"), "permissions", ["id"], unique=False)

    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "permission_id", name="uq_user_permissions_user_permission"
        ),
    )
    op.create_index(
        op.f("ix_user_permissions_id"), "user_permissions", ["id"], unique=False
    )
    op.create_index(
        "ix_user_permissions_user_id", "user_permissions", ["user_id"], unique=False
    )

    op.bulk_insert(
        permissions,
        [
            {"key": key, "name": name, "description": description, "sort_order": i}
            for i, (key, name, description) in enumerate(PERMISSIONS, start=1)
        ],
    )

    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO user_permissions (user_id, permission_id)
            SELECT u.id, p.id
            FROM users u CROSS JOIN permissions p
            WHERE u.role = 'USER'
              AND (
                p.key IN :legacy_keys
                OR (p.key = 'pagamentos' AND u.can_view_payments)
              )
            """
        ).bindparams(sa.bindparam("legacy_keys", expanding=True)),
        {"legacy_keys": list(LEGACY_USER_KEYS)},
    )

    op.drop_column("users", "can_view_payments")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_view_payments",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.get_bind().execute(
        sa.text(
            """
            UPDATE users SET can_view_payments = true
            WHERE id IN (
                SELECT up.user_id
                FROM user_permissions up
                JOIN permissions p ON p.id = up.permission_id
                WHERE p.key = 'pagamentos'
            )
            """
        )
    )

    op.drop_index("ix_user_permissions_user_id", table_name="user_permissions")
    op.drop_index(op.f("ix_user_permissions_id"), table_name="user_permissions")
    op.drop_table("user_permissions")
    op.drop_index(op.f("ix_permissions_id"), table_name="permissions")
    op.drop_table("permissions")
