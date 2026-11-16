from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.email.branding import (
    DEFAULT_ACCENT,
    DEFAULT_PRIMARY,
    OfficeBrandingProvider,
    build_branding,
)


def _config(**fields):
    return SimpleNamespace(**fields)


def test_uses_office_config_fields():
    branding = build_branding(
        _config(
            office_name="Souza Advocacia",
            logo_url="https://cdn.exemplo.com/logo.png",
            phone="(61) 3333-0000",
            color_bg_primary="#112233",
            color_buttons="#AA0000",
        )
    )
    assert branding["office"]["name"] == "Souza Advocacia"
    assert branding["office"]["logo_url"] == "https://cdn.exemplo.com/logo.png"
    assert branding["office"]["address"] is None
    assert branding["colors"]["primary"] == "#112233"
    assert branding["colors"]["accent"] == "#AA0000"


def test_rejects_non_hex_colors_and_non_http_urls():
    branding = build_branding(
        _config(
            color_bg_primary="red; background:url(x)",
            logo_url="javascript:alert(1)",
            website_url="ftp://x",
        )
    )
    assert branding["colors"]["primary"] == DEFAULT_PRIMARY
    assert branding["office"]["logo_url"] is None
    assert branding["office"]["website_url"] is None


def test_defaults_without_config():
    branding = build_branding(None, "Meu Escritório")
    assert branding["office"]["name"] == "Meu Escritório"
    assert branding["colors"]["accent"] == DEFAULT_ACCENT


class TestProvider:
    def _factory(self, counter: list):
        @contextmanager
        def session():
            counter.append(1)
            yield object()

        return session

    def test_caches_for_ttl(self):
        calls: list = []
        with patch("app.modules.email.branding.OfficeBrandingProvider._load") as load:
            load.return_value = {"office": {}, "colors": {}}
            provider = OfficeBrandingProvider(self._factory(calls), ttl_seconds=300)
            provider.get()
            provider.get()
            assert load.call_count == 1
            provider.invalidate()
            provider.get()
            assert load.call_count == 2

    def test_falls_back_when_office_config_missing(self):
        calls: list = []
        with patch(
            "app.modules.email.branding.OfficeConfigRepository.get_config",
            side_effect=RuntimeError("no row"),
        ):
            provider = OfficeBrandingProvider(self._factory(calls), fallback_name="X")
            branding = provider.get()
        assert branding["office"]["name"] == "X"
        assert branding["colors"]["primary"] == DEFAULT_PRIMARY
