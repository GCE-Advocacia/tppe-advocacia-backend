from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.modules.office_config.model import OfficeConfig
from app.modules.office_config.schema import (
    ListItem,
    OfficeConfigUpdate,
    ThemeCreate,
    ThemeDuplicate,
    ThemeUpdate,
)
from app.modules.office_config.service import OfficeConfigService
from app.shared.exceptions import ThemeNotFoundError


def make_config(**kwargs) -> OfficeConfig:
    defaults = {
        "id": 1,
        "office_name": None,
        "cnpj": None,
        "address": None,
        "phone": None,
        "email": None,
        "instagram_url": None,
        "linkedin_url": None,
        "whatsapp_url": None,
        "website_url": None,
        "hero_title": None,
        "hero_subtitle": None,
        "hero_image_url": None,
        "about_title": None,
        "about_description": None,
        "about_image_url": None,
        "lawyer_name": None,
        "lawyer_oab": None,
        "lawyer_description": None,
        "lawyer_image_url": None,
        "differentials": [],
        "areas_of_practice": [],
        "hero_image_position": None,
        "about_image_position": None,
        "lawyer_image_position": None,
        "color": None,
        "color_bg_primary": None,
        "color_bg_secondary": None,
        "color_bg_sobre": None,
        "color_buttons": None,
        "color_buttons_hover": None,
        "color_buttons_text": None,
        "color_title_primary": None,
        "color_title_secondary": None,
        "color_text_primary": None,
        "color_text_secondary": None,
        "color_link_primary": None,
        "color_link_secondary": None,
    }
    defaults.update(kwargs)
    config = MagicMock(spec=OfficeConfig)
    for key, value in defaults.items():
        setattr(config, key, value)
    return config


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    svc = OfficeConfigService.__new__(OfficeConfigService)
    svc.repository = repo
    return svc


class TestGet:
    def test_returns_office_config_orm(self, service, repo):
        config = make_config()
        repo.get_config.return_value = config
        assert service.get() is config

    def test_maps_fields_correctly(self, service, repo):
        repo.get_config.return_value = make_config(
            office_name="Escritório X", cnpj="00.000.000/0001-00"
        )
        result = service.get()
        assert result.office_name == "Escritório X"
        assert result.cnpj == "00.000.000/0001-00"

    def test_returns_raw_orm_values(self, service, repo):
        repo.get_config.return_value = make_config(
            differentials=None, areas_of_practice=None
        )
        result = service.get()
        assert result.differentials is None
        assert result.areas_of_practice is None


class TestUpdate:
    def test_calls_repository_with_set_fields_only(self, service, repo):
        repo.update_config.return_value = make_config(office_name="Novo")
        service.update(OfficeConfigUpdate(office_name="Novo"))
        repo.update_config.assert_called_once_with({"office_name": "Novo"})

    def test_excludes_unset_fields_from_update(self, service, repo):
        repo.update_config.return_value = make_config()
        service.update(OfficeConfigUpdate())
        repo.update_config.assert_called_once_with({})

    def test_includes_explicit_none_to_clear_field(self, service, repo):
        repo.update_config.return_value = make_config()
        service.update(OfficeConfigUpdate(office_name=None, hero_title=None))
        repo.update_config.assert_called_once_with(
            {"office_name": None, "hero_title": None}
        )

    def test_serializes_differentials_to_dicts(self, service, repo):
        repo.update_config.return_value = make_config(
            differentials=[{"title": "T", "description": "D"}]
        )
        service.update(
            OfficeConfigUpdate(differentials=[ListItem(title="T", description="D")])
        )
        call_data = repo.update_config.call_args[0][0]
        assert call_data["differentials"] == [{"title": "T", "description": "D"}]

    def test_serializes_areas_of_practice_to_dicts(self, service, repo):
        repo.update_config.return_value = make_config(
            areas_of_practice=[{"title": "A", "description": "B"}]
        )
        service.update(
            OfficeConfigUpdate(areas_of_practice=[ListItem(title="A", description="B")])
        )
        call_data = repo.update_config.call_args[0][0]
        assert call_data["areas_of_practice"] == [{"title": "A", "description": "B"}]

    def test_returns_office_config_orm(self, service, repo):
        config = make_config(office_name="X")
        repo.update_config.return_value = config
        result = service.update(OfficeConfigUpdate(office_name="X"))
        assert result is config
        assert result.office_name == "X"

    def test_can_update_image_position_fields(self, service, repo):
        repo.update_config.return_value = make_config(hero_image_position="50,50")
        service.update(OfficeConfigUpdate(hero_image_position="50,50"))
        repo.update_config.assert_called_once_with({"hero_image_position": "50,50"})

    def test_can_update_all_three_image_positions(self, service, repo):
        repo.update_config.return_value = make_config(
            hero_image_position="30,70",
            about_image_position="50,50",
            lawyer_image_position="80,20",
        )
        service.update(
            OfficeConfigUpdate(
                hero_image_position="30,70",
                about_image_position="50,50",
                lawyer_image_position="80,20",
            )
        )
        repo.update_config.assert_called_once_with(
            {
                "hero_image_position": "30,70",
                "about_image_position": "50,50",
                "lawyer_image_position": "80,20",
            }
        )

    def test_can_update_color(self, service, repo):
        repo.update_config.return_value = make_config(color="#1E3A8A")
        service.update(OfficeConfigUpdate(color="#1E3A8A"))
        repo.update_config.assert_called_once_with({"color": "#1E3A8A"})

    def test_can_update_landing_page_colors(self, service, repo):
        colors_payload = {
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
        repo.update_config.return_value = make_config(**colors_payload)
        service.update(OfficeConfigUpdate(**colors_payload))
        repo.update_config.assert_called_once_with(colors_payload)

    def test_update_with_nonexistent_theme_id_raises_not_found(self, service, repo):
        theme_repo = MagicMock()
        theme_repo.get_by_id.return_value = None
        service.theme_repository = theme_repo

        with pytest.raises(ThemeNotFoundError):
            service.update(OfficeConfigUpdate(theme_id=999999))

        theme_repo.get_by_id.assert_called_once_with(999999)
        repo.update_config.assert_not_called()

    def test_update_with_valid_theme_id_succeeds(self, service, repo):
        theme_repo = MagicMock()
        theme_repo.get_by_id.return_value = MagicMock(id=2)
        service.theme_repository = theme_repo
        repo.update_config.return_value = make_config()

        service.update(OfficeConfigUpdate(theme_id=2))

        theme_repo.get_by_id.assert_called_once_with(2)
        repo.update_config.assert_called_once_with({"theme_id": 2})

    def test_update_with_none_theme_id_skips_theme_lookup(self, service, repo):
        theme_repo = MagicMock()
        service.theme_repository = theme_repo
        repo.update_config.return_value = make_config()

        service.update(OfficeConfigUpdate(theme_id=None))

        theme_repo.get_by_id.assert_not_called()
        repo.update_config.assert_called_once_with({"theme_id": None})


class TestColorAndThemeNameValidation:
    @pytest.mark.parametrize(
        "field",
        ["color", "color_bg_primary", "color_buttons", "color_link_secondary"],
    )
    @pytest.mark.parametrize(
        "invalid_color", ["nao-eh-uma-cor", "rgb(0,0,0)", "#12345"]
    )
    def test_office_config_rejects_invalid_hex_colors(self, field, invalid_color):
        with pytest.raises(ValidationError):
            OfficeConfigUpdate(**{field: invalid_color})

    @pytest.mark.parametrize("blank_name", ["", "   ", "\t\n"])
    def test_theme_schemas_reject_whitespace_names(self, blank_name):
        base_colors = {
            "color_bg_primary": "#232C43",
            "color_bg_secondary": "#F5F3EF",
            "color_bg_sobre": "#FFFFFF",
            "color_buttons": "#661C16",
            "color_buttons_hover": "#A52020",
            "color_buttons_text": "#FFFFFF",
            "color_title_primary": "#FFFFFF",
            "color_title_secondary": "#232C43",
            "color_text_primary": "#FFFFFF",
            "color_text_secondary": "#6B7280",
            "color_link_primary": "#FFFFFF",
            "color_link_secondary": "#661C16",
        }
        with pytest.raises(ValidationError):
            ThemeCreate(name=blank_name, **base_colors)
        with pytest.raises(ValidationError):
            ThemeUpdate(name=blank_name)
        with pytest.raises(ValidationError):
            ThemeDuplicate(name=blank_name)

    def test_theme_schemas_strip_valid_names(self):
        assert ThemeUpdate(name="  Meu Tema  ").name == "Meu Tema"
        assert ThemeDuplicate(name="  Copia  ").name == "Copia"
