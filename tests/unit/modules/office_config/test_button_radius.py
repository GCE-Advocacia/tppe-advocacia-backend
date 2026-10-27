
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.modules.office_config.schema import OfficeConfigUpdate


@pytest.mark.parametrize("value", [f"{i}px" for i in range(25)] + ["999px"])
def test_accepts_presets_and_custom_pixel_values(value):
    assert OfficeConfigUpdate(button_radius=value).button_radius == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        12,
        True,
        "",
        "-1px",
        "25px",
        "998px",
        "1000px",
        "6em",
        "50%",
        "calc(6px)",
        "6px; color:red",
        "06px",
        "1.5px",
        "6px\n",
    ],
)
def test_rejects_values_outside_the_supported_geometry(value):
    with pytest.raises(ValidationError):
        OfficeConfigUpdate(button_radius=value)


def test_omitted_radius_does_not_reset_an_existing_preference():
    payload = OfficeConfigUpdate(office_name="Nome atualizado")
    assert "button_radius" not in payload.model_dump(exclude_unset=True)


def test_migration_backfills_existing_office_and_sets_default_for_new_rows():
    path = (
        Path(__file__).resolve().parents[4]
        / "alembic/versions/20261027_add_button_radius.py"
    )
    spec = importlib.util.spec_from_file_location("button_radius_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE office_config (id INTEGER PRIMARY KEY, color VARCHAR(50), logo_url VARCHAR(500))"
            )
        )
        connection.execute(
            text("INSERT INTO office_config VALUES (1, '#123456', 'logo.png')")
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        row = (
            connection.execute(text("SELECT * FROM office_config WHERE id = 1"))
            .mappings()
            .one()
        )
        assert dict(row) == {
            "id": 1,
            "color": "#123456",
            "logo_url": "logo.png",
            "button_radius": "6px",
        }
        connection.execute(text("INSERT INTO office_config (id) VALUES (2)"))
        assert (
            connection.execute(
                text("SELECT button_radius FROM office_config WHERE id = 2")
            ).scalar_one()
            == "6px"
        )
        column = next(
            c
            for c in inspect(connection).get_columns("office_config")
            if c["name"] == "button_radius"
        )
        assert column["type"].length == 20
        assert column["nullable"] is False
        migration.downgrade()
        assert "button_radius" not in {
            c["name"] for c in inspect(connection).get_columns("office_config")
        }
        assert (
            connection.execute(
                text("SELECT logo_url FROM office_config WHERE id = 1")
            ).scalar_one()
            == "logo.png"
        )
    engine.dispose()
