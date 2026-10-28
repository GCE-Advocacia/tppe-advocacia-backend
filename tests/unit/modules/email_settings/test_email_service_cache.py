from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.config.settings import Settings
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.shared.crypto import TokenCipher
from app.shared.deps import email as email_deps

KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _settings() -> Settings:
    return Settings(
        JWT_SECRET_KEY="x" * 40,
        APP_ENV="development",
        EMAIL_PROVIDERS="",
        EMAIL_ENCRYPTION_KEYS=KEY,
        _env_file=None,
    )


def _profile(id: int = 1, version: int = 1, host: str = "smtp.a.com"):
    return SimpleNamespace(
        id=id,
        version=version,
        provider="smtp",
        host=host,
        port=587,
        security="starttls",
        username="u",
        secret_encrypted=TokenCipher(KEY).encrypt("p"),
        from_email="a@a.com",
        from_name=None,
        reply_to=None,
    )


class FakeRepo:
    profiles: list = []
    error: Exception | None = None

    def __init__(self, db) -> None:
        pass

    def active_versions(self):
        if FakeRepo.error:
            raise FakeRepo.error
        return tuple((p.id, p.version) for p in FakeRepo.profiles)

    def list_active(self):
        return list(FakeRepo.profiles)


@pytest.fixture
def cache(monkeypatch):
    FakeRepo.profiles = []
    FakeRepo.error = None
    monkeypatch.setattr(email_deps, "EmailProfileRepository", FakeRepo)
    return email_deps.EmailServiceCache(lambda: nullcontext(), _settings())


def test_without_profiles_falls_back_to_env(cache):
    assert isinstance(cache.get(), FakeEmailService)


def test_builds_chain_from_saved_profiles(cache):
    FakeRepo.profiles = [_profile()]

    service = cache.get()

    assert isinstance(service, FailoverEmailService)
    assert service.providers[0].config.host == "smtp.a.com"
    assert service.providers[0].config.password == "p"


def test_same_version_reuses_chain(cache):
    FakeRepo.profiles = [_profile()]

    assert cache.get() is cache.get()


def test_new_version_rebuilds_chain(cache):
    FakeRepo.profiles = [_profile(version=1, host="smtp.a.com")]
    first = cache.get()

    FakeRepo.profiles = [_profile(version=2, host="smtp.b.com")]
    second = cache.get()

    assert second is not first
    assert second.providers[0].config.host == "smtp.b.com"


def test_database_error_keeps_current_chain(cache):
    FakeRepo.profiles = [_profile()]
    first = cache.get()

    FakeRepo.error = OperationalError("select", {}, Exception("db down"))

    assert cache.get() is first
