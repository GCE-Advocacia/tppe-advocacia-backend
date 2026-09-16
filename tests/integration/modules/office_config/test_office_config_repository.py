import pytest

from app.modules.office_config.model import (
    OfficeConfig,  # noqa: F401 — registers with Base
)
from app.modules.office_config.repository import OfficeConfigRepository


@pytest.fixture(autouse=True)
def seed_config(db):
    db.add(OfficeConfig(id=1, differentials=[], areas_of_practice=[]))
    db.commit()


class TestGetConfig:
    def test_returns_row_with_id_1(self, db):
        config = OfficeConfigRepository(db).get_config()
        assert config.id == 1

    def test_string_fields_are_none_by_default(self, db):
        config = OfficeConfigRepository(db).get_config()
        assert config.office_name is None
        assert config.hero_title is None
        assert config.lawyer_name is None
        assert config.hero_image_position is None
        assert config.about_image_position is None
        assert config.lawyer_image_position is None
        assert config.color is None
        assert config.color_bg_primary is None
        assert config.color_bg_secondary is None
        assert config.color_bg_sobre is None
        assert config.color_buttons is None
        assert config.color_buttons_hover is None
        assert config.color_buttons_text is None
        assert config.color_title_primary is None
        assert config.color_title_secondary is None
        assert config.color_text_primary is None
        assert config.color_text_secondary is None
        assert config.color_link_primary is None
        assert config.color_link_secondary is None

    def test_list_fields_are_empty_by_default(self, db):
        config = OfficeConfigRepository(db).get_config()
        assert config.differentials == []
        assert config.areas_of_practice == []


class TestUpdateConfig:
    def test_patches_string_field(self, db):
        result = OfficeConfigRepository(db).update_config(
            {"office_name": "Test Office"}
        )
        assert result.office_name == "Test Office"

    def test_untouched_fields_remain_none(self, db):
        result = OfficeConfigRepository(db).update_config({"office_name": "X"})
        assert result.cnpj is None
        assert result.phone is None

    def test_updates_differentials_json(self, db):
        items = [
            {"title": "T1", "description": "D1"},
            {"title": "T2", "description": "D2"},
        ]
        result = OfficeConfigRepository(db).update_config({"differentials": items})
        assert result.differentials == items

    def test_updates_areas_of_practice_json(self, db):
        items = [{"title": "A", "description": "B"}]
        result = OfficeConfigRepository(db).update_config({"areas_of_practice": items})
        assert result.areas_of_practice == items

    def test_replaces_list_on_second_update(self, db):
        repo = OfficeConfigRepository(db)
        repo.update_config({"differentials": [{"title": "Old", "description": "X"}]})
        result = repo.update_config(
            {"differentials": [{"title": "New", "description": "Y"}]}
        )
        assert len(result.differentials) == 1
        assert result.differentials[0]["title"] == "New"

    def test_multiple_fields_updated_at_once(self, db):
        result = OfficeConfigRepository(db).update_config(
            {
                "office_name": "Firm",
                "cnpj": "12.345.678/0001-99",
                "phone": "61 9999-0000",
            }
        )
        assert result.office_name == "Firm"
        assert result.cnpj == "12.345.678/0001-99"
        assert result.phone == "61 9999-0000"

    def test_patches_hero_image_position(self, db):
        result = OfficeConfigRepository(db).update_config(
            {"hero_image_position": "30,70"}
        )
        assert result.hero_image_position == "30,70"

    def test_patches_all_image_positions(self, db):
        result = OfficeConfigRepository(db).update_config(
            {
                "hero_image_position": "30,70",
                "about_image_position": "50,50",
                "lawyer_image_position": "80,20",
            }
        )
        assert result.hero_image_position == "30,70"
        assert result.about_image_position == "50,50"
        assert result.lawyer_image_position == "80,20"

    def test_image_position_update_does_not_affect_other_fields(self, db):
        repo = OfficeConfigRepository(db)
        repo.update_config({"office_name": "Escritório"})
        result = repo.update_config({"hero_image_position": "50,50"})
        assert result.office_name == "Escritório"

    def test_patches_color(self, db):
        result = OfficeConfigRepository(db).update_config({"color": "#1E3A8A"})
        assert result.color == "#1E3A8A"

    def test_patches_all_landing_page_colors(self, db):
        colors = {
            "color_bg_primary": "#111111",
            "color_bg_secondary": "#222222",
            "color_bg_sobre": "#333333",
            "color_buttons": "#444444",
            "color_buttons_hover": "#445566",
            "color_buttons_text": "#ffffff",
            "color_title_primary": "#555555",
            "color_title_secondary": "#666666",
            "color_text_primary": "#777777",
            "color_text_secondary": "#888888",
            "color_link_primary": "#999999",
            "color_link_secondary": "#aaaaaa",
        }
        result = OfficeConfigRepository(db).update_config(colors)
        assert result.color_bg_primary == "#111111"
        assert result.color_bg_secondary == "#222222"
        assert result.color_bg_sobre == "#333333"
        assert result.color_buttons == "#444444"
        assert result.color_buttons_hover == "#445566"
        assert result.color_buttons_text == "#ffffff"
        assert result.color_title_primary == "#555555"
        assert result.color_title_secondary == "#666666"
        assert result.color_text_primary == "#777777"
        assert result.color_text_secondary == "#888888"
        assert result.color_link_primary == "#999999"
        assert result.color_link_secondary == "#aaaaaa"
