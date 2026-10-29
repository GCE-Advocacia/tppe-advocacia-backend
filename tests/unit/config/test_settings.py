import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "APP_ENV": "development",
        "JWT_SECRET_KEY": "x" * 64,
        "RESEND_API_KEY": "re_test",
    }
    base.update(overrides)
    return base


class TestJwtSecretValidator:
    def test_accepts_weak_secret_outside_production(self, monkeypatch):
        for key, value in _env(JWT_SECRET_KEY="your-secret-key").items():
            monkeypatch.setenv(key, value)
        Settings(_env_file=None)

    def test_rejects_known_default_in_production(self, monkeypatch):
        for key, value in _env(
            APP_ENV="production", JWT_SECRET_KEY="your-secret-key"
        ).items():
            monkeypatch.setenv(key, value)
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "JWT_SECRET_KEY" in str(exc.value)

    def test_rejects_short_secret_in_production(self, monkeypatch):
        for key, value in _env(APP_ENV="production", JWT_SECRET_KEY="x" * 16).items():
            monkeypatch.setenv(key, value)
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "JWT_SECRET_KEY" in str(exc.value)

    def test_accepts_strong_secret_in_production(self, monkeypatch):
        for key, value in _env(
            APP_ENV="production",
            JWT_SECRET_KEY="x" * 32,
            MEDIA_BUCKET="uploads",
            DOCUMENT_STORAGE="drive",
        ).items():
            monkeypatch.setenv(key, value)
        Settings(_env_file=None)


class TestMediaBucketValidator:
    def test_allows_local_media_outside_production(self, monkeypatch):
        for key, value in _env().items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("MEDIA_BUCKET", raising=False)
        assert Settings(_env_file=None).media_bucket == ""

    def test_requires_bucket_in_production(self, monkeypatch):
        for key, value in _env(APP_ENV="production").items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("MEDIA_BUCKET", raising=False)
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "MEDIA_BUCKET" in str(exc.value)


class TestDocumentStorageValidator:
    def test_defaults_to_local_outside_production(self, monkeypatch):
        for key, value in _env().items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("DOCUMENT_STORAGE", raising=False)
        assert Settings(_env_file=None).document_storage == "local"

    def test_requires_drive_in_production(self, monkeypatch):
        for key, value in _env(APP_ENV="production", MEDIA_BUCKET="uploads").items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("DOCUMENT_STORAGE", raising=False)
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "DOCUMENT_STORAGE" in str(exc.value)

    def test_accepts_drive_in_production(self, monkeypatch):
        for key, value in _env(
            APP_ENV="production", MEDIA_BUCKET="uploads", DOCUMENT_STORAGE="drive"
        ).items():
            monkeypatch.setenv(key, value)
        assert Settings(_env_file=None).document_storage == "drive"
