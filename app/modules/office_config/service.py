MAX_TOTAL_THEMES = 9
MAX_CUSTOM_THEMES = 6

from fastapi import UploadFile

from app.modules.media.logo import normalize_favicon, normalize_logo
from app.modules.media.storage.logo import LogoStorage
from app.modules.office_config.model import LandingPageTheme, OfficeConfig
from app.modules.office_config.repository import OfficeConfigRepository, ThemeRepository
from app.modules.office_config.schema import (
    LogoSettingsUpdate,
    LogoSlot,
    OfficeConfigUpdate,
    ThemeCreate,
    ThemeUpdate,
)
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import (
    LogoNotConfiguredError,
    PredefinedThemeCannotBeDeletedError,
    ThemeLimitExceededError,
    ThemeNotFoundError,
)


LOGO_FIELDS: dict[LogoSlot, str] = {
    "landing-light": "logo_url",
    "landing-dark": "logo_dark_url",
    "system-light": "system_logo_url",
    "system-dark": "system_logo_dark_url",
    "favicon": "favicon_url",
}

DEFAULT_LOGO_FIELDS = {slot: f"default_{field}" for slot, field in LOGO_FIELDS.items()}
ASSET_FIELDS = (*LOGO_FIELDS.values(), *DEFAULT_LOGO_FIELDS.values())


class OfficeConfigService:
    def __init__(
        self,
        repository: OfficeConfigRepository,
        logo_storage: LogoStorage | None = None,
    ) -> None:
        self.repository = repository
        self.logo_storage = logo_storage or LogoStorage()

    def get(self) -> OfficeConfig:
        return self.repository.get_config()

    def update(self, payload: OfficeConfigUpdate) -> OfficeConfig:
        data = payload.model_dump(mode="json", exclude_unset=True)
        with unit_of_work(self.repository.db):
            return self.repository.update_config(data)

    def update_logo_settings(self, payload: LogoSettingsUpdate) -> OfficeConfig:
        with unit_of_work(self.repository.db):
            self.repository.get_config_for_update()
            return self.repository.update_config(payload.model_dump(exclude_unset=True))

    def preview_logo(self, file: UploadFile, slot: LogoSlot = "landing-light") -> bytes:
        return normalize_favicon(file) if slot == "favicon" else normalize_logo(file)

    def _apply_assets(
        self, config: OfficeConfig, changes: dict
    ) -> tuple[OfficeConfig, set]:
        before = {getattr(config, name) for name in ASSET_FIELDS}
        after = {changes.get(name, getattr(config, name)) for name in ASSET_FIELDS}
        return self.repository.update_config(changes), before - after

    def _cleanup(self, obsolete: set, base_url: str) -> None:
        for url in obsolete:
            self.logo_storage.delete_url(url, base_url)

    def update_logo(
        self,
        file: UploadFile,
        base_url: str,
        slot: LogoSlot = "landing-light",
        make_default: bool = False,
    ) -> OfficeConfig:
        content = self.preview_logo(file, slot)
        filename = None
        try:
            with unit_of_work(self.repository.db):
                config = self.repository.get_config_for_update()
                filename = self.logo_storage.save(content)
                url = self.logo_storage.url(filename, base_url)
                changes = {LOGO_FIELDS[slot]: url}
                if make_default:
                    changes[DEFAULT_LOGO_FIELDS[slot]] = url
                config, obsolete = self._apply_assets(config, changes)
        except Exception:
            if filename:
                self.logo_storage.delete(filename)
            raise
        self._cleanup(obsolete, base_url)
        return config

    def set_logo_default(
        self, base_url: str, slot: LogoSlot = "landing-light"
    ) -> OfficeConfig:
        with unit_of_work(self.repository.db):
            config = self.repository.get_config_for_update()
            current_url = getattr(config, LOGO_FIELDS[slot])
            if not current_url:
                raise LogoNotConfiguredError()
            config, obsolete = self._apply_assets(
                config, {DEFAULT_LOGO_FIELDS[slot]: current_url}
            )
        self._cleanup(obsolete, base_url)
        return config

    def reset_logo(
        self, base_url: str, slot: LogoSlot = "landing-light", factory: bool = False
    ) -> OfficeConfig:
        with unit_of_work(self.repository.db):
            config = self.repository.get_config_for_update()
            changes = {
                LOGO_FIELDS[slot]: None
                if factory
                else getattr(config, DEFAULT_LOGO_FIELDS[slot])
            }
            if factory:
                changes[DEFAULT_LOGO_FIELDS[slot]] = None
            config, obsolete = self._apply_assets(config, changes)
        self._cleanup(obsolete, base_url)
        return config


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
            "theme_id": theme.id,
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
