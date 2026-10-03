MAX_TOTAL_THEMES = 9
MAX_CUSTOM_THEMES = 6

from app.modules.office_config.model import LandingPageTheme, OfficeConfig
from app.modules.office_config.repository import OfficeConfigRepository, ThemeRepository
from app.modules.office_config.schema import OfficeConfigUpdate, ThemeCreate, ThemeUpdate
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import (
    PredefinedThemeCannotBeDeletedError,
    ThemeLimitExceededError,
    ThemeNotFoundError,
)


class OfficeConfigService:
    def __init__(self, repository: OfficeConfigRepository) -> None:
        self.repository = repository

    def get(self) -> OfficeConfig:
        return self.repository.get_config()

    def update(self, payload: OfficeConfigUpdate) -> OfficeConfig:
        data = payload.model_dump(mode="json", exclude_unset=True)
        with unit_of_work(self.repository.db):
            return self.repository.update_config(data)


class ThemeService:
    def __init__(
        self,
        repository: ThemeRepository,
        office_config_repo: OfficeConfigRepository,
    ) -> None:
        self.repository = repository
        self.office_config_repo = office_config_repo

    def list(self) -> list[LandingPageTheme]:
        return self.repository.list_themes()

    def get_quota(self) -> dict:
        total_count = self.repository.count_themes()
        custom_count = self.repository.count_custom_themes()
        return {
            "max_total": MAX_TOTAL_THEMES,
            "max_custom": MAX_CUSTOM_THEMES,
            "total_count": total_count,
            "custom_count": custom_count,
            "is_limit_reached": (
                custom_count >= MAX_CUSTOM_THEMES or total_count >= MAX_TOTAL_THEMES
            ),
        }

    def get_by_id(self, theme_id: int) -> LandingPageTheme:
        theme = self.repository.get_by_id(theme_id)
        if not theme:
            raise ThemeNotFoundError()
        return theme

    def create(self, payload: ThemeCreate) -> LandingPageTheme:
        total_count = self.repository.count_themes()
        if total_count >= MAX_TOTAL_THEMES:
            raise ThemeLimitExceededError()
        custom_count = self.repository.count_custom_themes()
        if custom_count >= MAX_CUSTOM_THEMES:
            raise ThemeLimitExceededError()

        data = payload.model_dump(mode="json")
        data["is_predefined"] = False
        with unit_of_work(self.repository.db):
            return self.repository.create_theme(data)

    def update(self, theme_id: int, payload: ThemeUpdate) -> LandingPageTheme:
        theme = self.repository.get_by_id(theme_id)
        if not theme:
            raise ThemeNotFoundError()

        data = payload.model_dump(mode="json", exclude_unset=True)
        data.pop("is_predefined", None)
        with unit_of_work(self.repository.db):
            return self.repository.update_theme(theme, data)

    def delete(self, theme_id: int) -> None:
        theme = self.repository.get_by_id(theme_id)
        if not theme:
            raise ThemeNotFoundError()
        if theme.is_predefined:
            raise PredefinedThemeCannotBeDeletedError()
        with unit_of_work(self.repository.db):
            self.repository.delete_theme(theme)

    def apply(self, theme_id: int) -> OfficeConfig:
        theme = self.repository.get_by_id(theme_id)
        if not theme:
            raise ThemeNotFoundError()

        color_data = {
            "color": theme.color,
            "color_bg_primary": theme.color_bg_primary,
            "color_bg_secondary": theme.color_bg_secondary,
            "color_bg_sobre": theme.color_bg_sobre,
            "color_buttons": theme.color_buttons,
            "color_buttons_hover": theme.color_buttons_hover,
            "color_buttons_text": theme.color_buttons_text,
            "color_title_primary": theme.color_title_primary,
            "color_title_secondary": theme.color_title_secondary,
            "color_text_primary": theme.color_text_primary,
            "color_text_secondary": theme.color_text_secondary,
            "color_link_primary": theme.color_link_primary,
            "color_link_secondary": theme.color_link_secondary,
        }
        with unit_of_work(self.office_config_repo.db):
            return self.office_config_repo.update_config(color_data)
