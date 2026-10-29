"""Upgrading a previously configured office must keep the published logo."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_upgrade_preserves_legacy_logo_and_starts_in_shared_mode():
    path = (
        Path(__file__).resolve().parents[4]
        / "alembic/versions/20261003_add_branding_variants.py"
    )
    spec = importlib.util.spec_from_file_location("branding_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TABLE office_config (
                id INTEGER PRIMARY KEY, logo_url VARCHAR(500),
                logo_original_url VARCHAR(500), logo_remove_background BOOLEAN,
                logo_background_tolerance INTEGER, color VARCHAR(50)
            )
        """)
        )
        connection.execute(
            text("""
            INSERT INTO office_config VALUES (1, 'published.png', 'original.png', 1, 30, '#123456')
        """)
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        row = connection.execute(text("SELECT * FROM office_config")).mappings().one()
        assert row["logo_url"] == "published.png"
        assert row["color"] == "#123456"
        for field in (
            "logo_same_for_themes",
            "system_logo_same_for_themes",
            "system_uses_landing_logo",
        ):
            assert row[field] == 1
        for field in (
            "logo_dark_url",
            "system_logo_url",
            "system_logo_dark_url",
            "favicon_url",
        ):
            assert row[field] is None
        assert "logo_remove_background" not in row
        assert "logo_original_url" not in row
        migration.downgrade()
        assert "logo_remove_background" in {
            col["name"] for col in inspect(connection).get_columns("office_config")
        }
        assert (
            connection.execute(text("SELECT logo_url FROM office_config")).scalar_one()
            == "published.png"
        )
    engine.dispose()


def test_defaults_migration_keeps_current_logos_and_downgrades_without_data_loss():
    path = (
        Path(__file__).resolve().parents[4]
        / "alembic/versions/20261004_add_logo_defaults.py"
    )
    spec = importlib.util.spec_from_file_location("defaults_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE office_config (id INTEGER PRIMARY KEY, logo_url VARCHAR(500), logo_dark_url VARCHAR(500), system_logo_url VARCHAR(500), system_logo_dark_url VARCHAR(500), favicon_url VARCHAR(500), color VARCHAR(50))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO office_config VALUES (1, 'light.png', 'dark.png', 'system.png', 'system-dark.png', 'icon.png', '#123456')"
            )
        )
        original = dict(
            connection.execute(text("SELECT * FROM office_config")).mappings().one()
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        row = connection.execute(text("SELECT * FROM office_config")).mappings().one()
        for key, value in original.items():
            assert row[key] == value
        for key in migration.FIELDS:
            assert row[key] is None
        migration.downgrade()
        assert (
            dict(
                connection.execute(text("SELECT * FROM office_config")).mappings().one()
            )
            == original
        )
    engine.dispose()
