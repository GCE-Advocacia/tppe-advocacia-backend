from fastapi import UploadFile

from app.modules.media.logo import normalize_favicon, normalize_logo
from app.modules.media.storage.logo import LogoStorage
from app.modules.office_config.model import OfficeConfig
from app.modules.office_config.repository import OfficeConfigRepository
from app.modules.office_config.schema import (
    LogoSettingsUpdate,
    LogoSlot,
    OfficeConfigUpdate,
)
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import LogoNotConfiguredError

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
