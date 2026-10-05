"""merge heads de cores, financeiro e pagamentos

As tres features saíram do mesmo pai (e5f6a7b8c9d0) e foram mergeadas sem
religar a cadeia, deixando tres heads simultaneos. Esta revisao apenas une
as pontas: nao ha DDL, cada head ja aplicou o seu.

Revision ID: b1c2d3e4f5a6
Revises: d4e5f6a7b8c9, f6a7b8c9d0e1, 44d4da2b8fa6
Create Date: 2026-09-17
"""

revision = "b1c2d3e4f5a6"
down_revision = ("d4e5f6a7b8c9", "f6a7b8c9d0e1", "44d4da2b8fa6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
