from unittest.mock import MagicMock
import pytest

from app.modules.office_config.model import LandingPageTheme, OfficeConfig
from app.modules.office_config.schema import ThemeCreate, ThemeUpdate
from app.modules.office_config.service import ThemeService
from app.shared.exceptions import (
    PredefinedThemeCannotBeDeletedError,
    ThemeLimitExceededError,
    ThemeNotFoundError,
)


def make_theme(**kwargs) -> LandingPageTheme:
    defaults = {
        "id": 1,
        "name": "Tema Teste",
        "description": "Desc Teste",
        "is_predefined": False,
        "color": "#111111",
        "color_bg_primary": "#222222",
        "color_bg_secondary": "#333333",
        "color_bg_sobre": "#444444",
        "color_buttons": "#555555",
        "color_buttons_hover": "#666666",
        "color_buttons_text": "#777777",
        "color_title_primary": "#888888",
        "color_title_secondary": "#999999",
        "color_text_primary": "#aaaaaa",
        "color_text_secondary": "#bbbbbb",
        "color_link_primary": "#cccccc",
        "color_link_secondary": "#dddddd",
    }
    defaults.update(kwargs)
    theme = MagicMock(spec=LandingPageTheme)
    for key, value in defaults.items():
        setattr(theme, key, value)
    return theme


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def office_config_repo():
    return MagicMock()


@pytest.fixture
def service(repo, office_config_repo):
    svc = ThemeService.__new__(ThemeService)
    svc.repository = repo
    svc.office_config_repo = office_config_repo
    return svc


class TestThemeListAndGet:
    def test_list_returns_themes(self, service, repo):
        theme1 = make_theme(id=1, name="T1", is_predefined=True)
        theme2 = make_theme(id=2, name="T2", is_predefined=False)
        repo.list_themes.return_value = [theme1, theme2]

        result = service.list()
        assert result == [theme1, theme2]
        repo.list_themes.assert_called_once()

    def test_get_by_id_success(self, service, repo):
        theme = make_theme(id=1)
        repo.get_by_id.return_value = theme

        result = service.get_by_id(1)
        assert result == theme
        repo.get_by_id.assert_called_once_with(1)

    def test_get_by_id_not_found(self, service, repo):
        repo.get_by_id.return_value = None
        with pytest.raises(ThemeNotFoundError):
            service.get_by_id(999)


class TestThemeCreate:
    @pytest.fixture
    def payload(self):
        return ThemeCreate(
            name="Novo Tema",
            description="Descrição do tema",
            color="#121212",
            color_bg_primary="#121212",
            color_bg_secondary="#f0f0f0",
            color_bg_sobre="#ffffff",
            color_buttons="#c5a059",
            color_buttons_hover="#a38038",
            color_buttons_text="#ffffff",
            color_title_primary="#ffffff",
            color_title_secondary="#121212",
            color_text_primary="#ffffff",
            color_text_secondary="#555555",
            color_link_primary="#ffffff",
            color_link_secondary="#c5a059",
        )

    def test_create_theme_success(self, service, repo, payload):
        repo.count_themes.return_value = 4
        repo.count_custom_themes.return_value = 0
        created = make_theme(id=5, name=payload.name)
        repo.create_theme.return_value = created

        result = service.create(payload)
        assert result == created
        call_data = repo.create_theme.call_args[0][0]
        assert call_data["name"] == "Novo Tema"
        assert call_data["is_predefined"] is False

    def test_create_theme_exceeds_total_limit(self, service, repo, payload):
        repo.count_themes.return_value = 10
        with pytest.raises(ThemeLimitExceededError):
            service.create(payload)

    def test_create_theme_exceeds_custom_limit(self, service, repo, payload):
        repo.count_themes.return_value = 8
        repo.count_custom_themes.return_value = 6
        with pytest.raises(ThemeLimitExceededError):
            service.create(payload)


class TestThemeUpdate:
    def test_update_theme_success(self, service, repo):
        theme = make_theme(id=2, name="Tema Antigo")
        repo.get_by_id.return_value = theme
        updated = make_theme(id=2, name="Tema Novo")
        repo.update_theme.return_value = updated

        payload = ThemeUpdate(name="Tema Novo")
        result = service.update(2, payload)

        assert result == updated
        repo.update_theme.assert_called_once_with(theme, {"name": "Tema Novo"})

    def test_update_theme_not_found(self, service, repo):
        repo.get_by_id.return_value = None
        with pytest.raises(ThemeNotFoundError):
            service.update(999, ThemeUpdate(name="Qualquer"))


class TestThemeDelete:
    def test_delete_custom_theme_success(self, service, repo):
        theme = make_theme(id=5, is_predefined=False)
        repo.get_by_id.return_value = theme

        service.delete(5)
        repo.delete_theme.assert_called_once_with(theme)

    def test_delete_predefined_theme_raises_error(self, service, repo):
        theme = make_theme(id=1, is_predefined=True)
        repo.get_by_id.return_value = theme

        with pytest.raises(PredefinedThemeCannotBeDeletedError):
            service.delete(1)
        repo.delete_theme.assert_not_called()

    def test_delete_not_found_raises_error(self, service, repo):
        repo.get_by_id.return_value = None
        with pytest.raises(ThemeNotFoundError):
            service.delete(999)


class TestThemeApply:
    def test_apply_theme_updates_office_config(self, service, repo, office_config_repo):
        theme = make_theme(
            id=1,
            color="#111111",
            color_bg_primary="#222222",
            color_bg_secondary="#333333",
            color_bg_sobre="#444444",
            color_buttons="#555555",
            color_buttons_hover="#666666",
            color_buttons_text="#777777",
            color_title_primary="#888888",
            color_title_secondary="#999999",
            color_text_primary="#aaaaaa",
            color_text_secondary="#bbbbbb",
            color_link_primary="#cccccc",
            color_link_secondary="#dddddd",
        )
        repo.get_by_id.return_value = theme
        config_mock = MagicMock(spec=OfficeConfig)
        office_config_repo.update_config.return_value = config_mock

        result = service.apply(1)
        assert result == config_mock
        office_config_repo.update_config.assert_called_once_with(
            {
                "color": "#111111",
                "color_bg_primary": "#222222",
                "color_bg_secondary": "#333333",
                "color_bg_sobre": "#444444",
                "color_buttons": "#555555",
                "color_buttons_hover": "#666666",
                "color_buttons_text": "#777777",
                "color_title_primary": "#888888",
                "color_title_secondary": "#999999",
                "color_text_primary": "#aaaaaa",
                "color_text_secondary": "#bbbbbb",
                "color_link_primary": "#cccccc",
                "color_link_secondary": "#dddddd",
            }
        )

    def test_apply_theme_not_found(self, service, repo):
        repo.get_by_id.return_value = None
        with pytest.raises(ThemeNotFoundError):
            service.apply(999)
