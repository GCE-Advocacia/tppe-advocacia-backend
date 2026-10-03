import pytest

from app.modules.office_config.model import LandingPageTheme
from app.modules.office_config.repository import ThemeRepository


@pytest.fixture
def repo(db):
    return ThemeRepository(db)


def sample_theme_data(name="Tema 1", is_predefined=False) -> dict:
    return {
        "name": name,
        "description": "Descrição",
        "is_predefined": is_predefined,
        "color": "#232C43",
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


class TestThemeRepository:
    def test_create_and_get_by_id(self, db, repo):
        data = sample_theme_data("Tema Criado")
        theme = repo.create_theme(data)
        db.commit()

        found = repo.get_by_id(theme.id)
        assert found is not None
        assert found.name == "Tema Criado"
        assert found.color == "#232C43"
        assert found.is_predefined is False

    def test_list_themes_orders_predefined_first(self, db, repo):
        custom = repo.create_theme(sample_theme_data("Custom", is_predefined=False))
        predef = repo.create_theme(sample_theme_data("Predefined", is_predefined=True))
        db.commit()

        themes = repo.list_themes()
        assert len(themes) == 2
        assert themes[0].id == predef.id
        assert themes[0].is_predefined is True
        assert themes[1].id == custom.id
        assert themes[1].is_predefined is False

    def test_count_themes_and_custom_themes(self, db, repo):
        assert repo.count_themes() == 0
        assert repo.count_custom_themes() == 0

        repo.create_theme(sample_theme_data("P1", is_predefined=True))
        repo.create_theme(sample_theme_data("P2", is_predefined=True))
        repo.create_theme(sample_theme_data("C1", is_predefined=False))
        db.commit()

        assert repo.count_themes() == 3
        assert repo.count_custom_themes() == 1

    def test_update_theme(self, db, repo):
        theme = repo.create_theme(sample_theme_data("Original"))
        db.commit()

        updated = repo.update_theme(theme, {"name": "Modificado", "color_buttons": "#000000"})
        db.commit()

        assert updated.name == "Modificado"
        assert updated.color_buttons == "#000000"

    def test_delete_theme(self, db, repo):
        theme = repo.create_theme(sample_theme_data("Para Deletar"))
        db.commit()
        theme_id = theme.id

        repo.delete_theme(theme)
        db.commit()

        assert repo.get_by_id(theme_id) is None
