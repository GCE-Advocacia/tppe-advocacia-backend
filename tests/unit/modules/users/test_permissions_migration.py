"""Permissões de funcionários existentes sobrevivem ao upgrade e downgrade."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_migrates_existing_users_and_restores_legacy_flag_on_downgrade():
    path = (
        Path(__file__).resolve().parents[4]
        / "alembic/versions/20261026_add_permissions_tables.py"
    )
    spec = importlib.util.spec_from_file_location("permissions_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY, role VARCHAR(10), can_view_payments BOOLEAN
                )
            """)
        )
        connection.execute(
            text("""
                INSERT INTO users (id, role, can_view_payments)
                VALUES (1, 'USER', 1), (2, 'USER', 0), (3, 'ADMIN', 0)
            """)
        )
        migration.op = Operations(MigrationContext.configure(connection))

        for _ in range(2):
            migration.upgrade()
            rows = connection.execute(
                text("""
                    SELECT u.id, p.key FROM users u
                    JOIN user_permissions up ON up.user_id = u.id
                    JOIN permissions p ON p.id = up.permission_id
                    ORDER BY u.id, p.sort_order
                """)
            ).all()
            base_keys = [
                "artigos",
                "clientes",
                "agenda",
                "processos",
                "tarefas",
                "notificacoes",
            ]
            assert [key for user_id, key in rows if user_id == 1] == [
                "artigos",
                "clientes",
                "agenda",
                "pagamentos",
                "processos",
                "tarefas",
                "notificacoes",
            ]
            assert [key for user_id, key in rows if user_id == 2] == base_keys
            assert not [key for user_id, key in rows if user_id == 3]

            migration.downgrade()
            flags = connection.execute(
                text("SELECT id, can_view_payments FROM users ORDER BY id")
            ).all()
            assert flags == [(1, 1), (2, 0), (3, 0)]
