"""Identidade visual do escritório para os e-mails (logo, cores e contatos)."""

import logging
import re
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.modules.office_config.model import OfficeConfig
from app.modules.office_config.repository import OfficeConfigRepository

logger = logging.getLogger(__name__)

DEFAULT_PRIMARY = "#232C43"
DEFAULT_ACCENT = "#661C16"
DEFAULT_OFFICE_NAME = "Escritório de Advocacia"

# As cores vão para atributos style: só aceita hex, para nada do banco virar CSS.
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _color(value: str | None, default: str) -> str:
    return value if value and _HEX_COLOR.match(value.strip()) else default


def _http_url(value: str | None) -> str | None:
    if value and value.strip().lower().startswith(("http://", "https://")):
        return value.strip()
    return None


def default_branding(office_name: str | None = None) -> dict:
    return build_branding(None, office_name)


def build_branding(config: OfficeConfig | None, fallback_name: str | None = None) -> dict:
    """Monta o contexto ``office`` + ``colors``. Todas as chaves sempre existem
    (com ``None`` quando vazias), porque o renderer usa ``StrictUndefined``."""

    def get(attr: str) -> str | None:
        value = getattr(config, attr, None) if config is not None else None
        return value.strip() if isinstance(value, str) and value.strip() else None

    logo = _http_url(get("logo_url")) or _http_url(get("default_logo_url"))
    office = {
        "name": get("office_name") or fallback_name or DEFAULT_OFFICE_NAME,
        "logo_url": logo,
        "address": get("address"),
        "phone": get("phone"),
        "email": get("email"),
        "whatsapp_url": _http_url(get("whatsapp_url")),
        "website_url": _http_url(get("website_url")),
        "instagram_url": _http_url(get("instagram_url")),
        "linkedin_url": _http_url(get("linkedin_url")),
        "cnpj": get("cnpj"),
    }
    colors = {
        "primary": _color(get("color_bg_primary"), DEFAULT_PRIMARY),
        "accent": _color(get("color_buttons"), DEFAULT_ACCENT),
        "button_text": _color(get("color_buttons_text"), "#FFFFFF"),
        "link": _color(get("color_link_secondary"), DEFAULT_ACCENT),
        "muted": _color(get("color_text_secondary"), "#6B7280"),
    }
    return {"office": office, "colors": colors}


class OfficeBrandingProvider:
    """Lê o ``office_config`` com cache de ``ttl`` segundos por processo."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]],
        ttl_seconds: float = 300,
        fallback_name: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ttl = ttl_seconds
        self._fallback_name = fallback_name
        self._cached: dict | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def get(self) -> dict:
        with self._lock:
            now = time.monotonic()
            if self._cached is None or now >= self._expires_at:
                self._cached = self._load()
                self._expires_at = now + self._ttl
            return self._cached

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None

    def _load(self) -> dict:
        try:
            with self._session_factory() as db:
                config = OfficeConfigRepository(db).get_config()
                return build_branding(config, self._fallback_name)
        except Exception:
            # Sem office_config (ou banco fora): e-mail sai com a marca padrão.
            logger.warning("Could not load office_config for email branding", exc_info=True)
            return default_branding(self._fallback_name)


class StaticBrandingProvider:
    """Para testes e pré-visualizações com marca fixa."""

    def __init__(self, branding: dict | None = None) -> None:
        self._branding = branding or default_branding()

    def get(self) -> dict:
        return self._branding

    def invalidate(self) -> None:
        pass
