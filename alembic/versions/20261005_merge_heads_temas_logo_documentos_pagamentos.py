"""merge heads de temas, logo, documentos, permissao e lembretes de pagamento

As features saíram do mesmo pai (b1c2d3e4f5a6) e foram mergeadas sem
religar a cadeia, deixando cinco heads simultaneos. Esta revisao apenas une
as pontas: nao ha DDL, cada head ja aplicou o seu.

Revision ID: c1d2e3f4a5b6
Revises: f1a2b3c4d5e6, e0f1a2b3c4d5, b8c9d0e1f2a3, 587e82a35097, a9b8c7d6e5f4
Create Date: 2026-10-05
"""

revision = "c1d2e3f4a5b6"
down_revision = (
    "f1a2b3c4d5e6",
    "e0f1a2b3c4d5",
    "b8c9d0e1f2a3",
    "587e82a35097",
    "a9b8c7d6e5f4",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
