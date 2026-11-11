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


def test_system_button_colors_and_theme_presets_migration():
    path = (
        Path(__file__).resolve().parents[4]
        / "alembic/versions/20261028_add_system_button_colors_and_theme_presets.py"
    )
    spec = importlib.util.spec_from_file_location("system_buttons_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "9f0a1b2c3d4e"
    assert migration.down_revision == "8e9f0a1b2c3d"

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE landing_page_themes (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100),
                    is_predefined BOOLEAN,
                    color_buttons VARCHAR(50),
                    color_buttons_hover VARCHAR(50),
                    color_buttons_text VARCHAR(50)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE office_config (
                    id INTEGER PRIMARY KEY,
                    theme_id INTEGER,
                    color_buttons VARCHAR(50),
                    color_buttons_hover VARCHAR(50),
                    color_buttons_text VARCHAR(50)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO landing_page_themes VALUES
                (1, 'Clássico Navy & Wine (Padrão)', 1, '#661C16', '#A52020', '#FFFFFF'),
                (2, 'Dourado & Ônix Nobre', 1, '#C5A059', '#A38038', '#12161A')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO office_config VALUES (1, 1, '#661C16', '#A52020', '#FFFFFF')
                """
            )
        )

        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        rows = {
            r["id"]: r
            for r in connection.execute(text("SELECT * FROM landing_page_themes")).mappings().all()
        }
        # Clássico Navy & Wine -> Black system buttons pre-set
        assert rows[1]["system_uses_landing_buttons"] == 0
        assert rows[1]["color_buttons_system"] == "#111827"
        assert rows[1]["color_buttons_system_hover"] == "#1F2937"
        assert rows[1]["color_buttons_system_text"] == "#FFFFFF"

        # Dourado & Ônix -> follows landing buttons
        assert rows[2]["system_uses_landing_buttons"] == 1
        assert rows[2]["color_buttons_system"] == "#C5A059"

        # OfficeConfig updated to match default theme pre-set
        config_row = connection.execute(text("SELECT * FROM office_config")).mappings().one()
        assert config_row["system_uses_landing_buttons"] == 0
        assert config_row["color_buttons_system"] == "#111827"
        assert config_row["color_buttons_system_hover"] == "#1F2937"
        assert config_row["color_buttons_system_text"] == "#FFFFFF"

        migration.downgrade()
        theme_cols = {col["name"] for col in inspect(connection).get_columns("landing_page_themes")}
        config_cols = {col["name"] for col in inspect(connection).get_columns("office_config")}
        assert "system_uses_landing_buttons" not in theme_cols
        assert "color_buttons_system" not in theme_cols
        assert "system_uses_landing_buttons" not in config_cols
        assert "color_buttons_system" not in config_cols
    engine.dispose()


def test_alembic_has_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[4]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["9f0a1b2c3d4e"]


def test_office_config_update_schema_accepts_system_button_colors():
    from app.modules.office_config.schema import OfficeConfigUpdate

    payload = OfficeConfigUpdate(
        system_uses_landing_buttons=False,
        color_buttons_system="#123456",
        color_buttons_system_hover="#234567",
        color_buttons_system_text="#FFFFFF",
    )
    data = payload.model_dump(exclude_unset=True)
    assert data["system_uses_landing_buttons"] is False
    assert data["color_buttons_system"] == "#123456"
    assert data["color_buttons_system_hover"] == "#234567"
    assert data["color_buttons_system_text"] == "#FFFFFF"


def test_theme_create_and_update_schemas_support_system_buttons():
    from app.modules.office_config.schema import ThemeCreate, ThemeUpdate

    tc = ThemeCreate(
        name="Teste Tema",
        color_bg_primary="#111",
        color_bg_secondary="#222",
        color_bg_sobre="#333",
        color_buttons="#444",
        color_buttons_hover="#555",
        color_buttons_text="#666",
        color_title_primary="#777",
        color_title_secondary="#888",
        color_text_primary="#999",
        color_text_secondary="#aaa",
        color_link_primary="#bbb",
        color_link_secondary="#ccc",
        system_uses_landing_buttons=False,
        color_buttons_system="#000",
        color_buttons_system_hover="#111",
        color_buttons_system_text="#fff",
    )
    assert tc.system_uses_landing_buttons is False
    assert tc.color_buttons_system == "#000"

    tu = ThemeUpdate(system_uses_landing_buttons=True, color_buttons_system=None)
    dumped = tu.model_dump(exclude_unset=True)
    assert dumped["system_uses_landing_buttons"] is True
    assert dumped["color_buttons_system"] is None
