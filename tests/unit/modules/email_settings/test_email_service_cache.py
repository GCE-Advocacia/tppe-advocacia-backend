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


def _settings(**env) -> Settings:
    values = {
        "JWT_SECRET_KEY": "x" * 40,
        "APP_ENV": "development",
        "EMAIL_PROVIDERS": "",
        "EMAIL_ENCRYPTION_KEYS": KEY,
        **env,
    }
    return Settings(_env_file=None, **values)


def _system_settings() -> Settings:
    return _settings(
        EMAIL_PROVIDERS="smtp",
        SMTP_HOST="smtp.sistema.com",
        SMTP_FROM_EMAIL="noreply@sistema.com",
        SMTP_FROM_NAME="Sistema",
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
    identity = None
    error: Exception | None = None

    def __init__(self, db) -> None:
        pass

    def active_versions(self):
        if FakeRepo.error:
            raise FakeRepo.error
        return tuple((p.id, p.version) for p in FakeRepo.profiles)

    def identity_version(self):
        return FakeRepo.identity.version if FakeRepo.identity else 0

    def get_identity(self):
        return FakeRepo.identity

    def get_own_account(self):
        return FakeRepo.profiles[0] if FakeRepo.profiles else None


@pytest.fixture
def repo(monkeypatch):
    FakeRepo.profiles = []
    FakeRepo.identity = None
    FakeRepo.error = None
    monkeypatch.setattr(email_deps, "EmailProfileRepository", FakeRepo)
    return FakeRepo


@pytest.fixture
def cache(repo):
    return email_deps.EmailServiceCache(lambda: nullcontext(), _settings())


@pytest.fixture
def system_cache(repo):
    return email_deps.EmailServiceCache(lambda: nullcontext(), _system_settings())


def test_without_anything_uses_fake_in_dev(cache):
    assert isinstance(cache.get(), FakeEmailService)


def test_without_own_account_uses_system_account_with_office_identity(
    system_cache, repo
):
    repo.identity = SimpleNamespace(
        from_name="Souza & Lima", reply_to="contato@souzalima.adv.br", version=2
    )

    service = system_cache.get()

    assert service.provider_names == ["system"]
    config = service.providers[0].config
    assert config.host == "smtp.sistema.com"
    assert config.from_name == "Souza & Lima"
    assert config.reply_to == "contato@souzalima.adv.br"


def test_own_account_comes_first_and_system_is_the_fallback(system_cache, repo):
    repo.profiles = [_profile()]

    service = system_cache.get()

    assert service.provider_names == ["own", "system"]
    assert service.providers[0].config.host == "smtp.a.com"


def test_identity_change_rebuilds_chain(system_cache, repo):
    repo.identity = SimpleNamespace(from_name="A", reply_to=None, version=1)
    first = system_cache.get()

    repo.identity = SimpleNamespace(from_name="B", reply_to=None, version=2)
    second = system_cache.get()

    assert second is not first
    assert second.providers[0].config.from_name == "B"


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
