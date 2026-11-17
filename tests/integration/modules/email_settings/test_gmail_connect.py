from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.fernet import Fernet

from app.config.settings import get_settings
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.gmail_provider import GmailConfig
from app.modules.email.renderer import EmailRenderer
from app.modules.email_settings import gmail as gmail_module
from app.modules.email_settings.configs import decrypt_secret, profile_to_config
from app.modules.email_settings.gmail import (
    GMAIL_SCOPES,
    GmailConnectError,
    GmailConnectService,
    build_gmail_connect_service,
)
from app.modules.email_settings.messages import explain_gmail_error
from app.modules.email_settings.model import EmailIdentity, EmailProfile
from app.modules.email_settings.repository import EmailProfileRepository
from app.modules.email_settings.schema import EmailProfileUpdate
from app.modules.email_settings.service import EmailSettingsService
from app.modules.users.repository import UserRepository
from app.shared.exceptions import GmailNotConfiguredError
from app.shared.types import Role


def id_token(email="escritorio@gmail.com", verified=True) -> str:
    return jwt.encode(
        {"email": email, "email_verified": verified}, "x", algorithm="HS256"
    )


class FakeOAuth:
    def __init__(self, credentials=None, error: Exception | None = None) -> None:
        self.credentials = credentials or SimpleNamespace(
            refresh_token="refresh-1",
            id_token=id_token(),
            scopes=GMAIL_SCOPES,
            granted_scopes=GMAIL_SCOPES,
        )
        self.error = error
        self.states: list[str] = []

    def build_auth_url(self, state: str) -> str:
        self.states.append(state)
        return f"https://accounts.google.com/o/oauth2/auth?state={state}"

    def exchange(self, code: str):
        if self.error is not None:
            raise self.error
        return self.credentials


@pytest.fixture
def settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(
        settings, "email_encryption_keys", [Fernet.generate_key().decode()]
    )
    return settings


@pytest.fixture
def admin(db):
    user = UserRepository(db).create(
        name="Dra. Ana",
        email="ana@escritorio.com.br",
        hashed_password="x",
        role=Role.ADMIN,
    )
    db.commit()
    return user


@pytest.fixture
def collaborator(db):
    user = UserRepository(db).create(
        name="Beto", email="beto@escritorio.com.br", hashed_password="x", role=Role.USER
    )
    db.commit()
    return user


@pytest.fixture
def primary(db):
    profile = EmailProfile(
        name="Primário", priority=1, provider="smtp", security="starttls"
    )
    db.add(profile)
    db.add(EmailIdentity(id=1, version=1))
    db.commit()
    return profile


@pytest.fixture
def revoked(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(gmail_module, "_revoke", calls.append)
    return calls


def make(db, settings, oauth=None, audit=None) -> GmailConnectService:
    return GmailConnectService(
        EmailProfileRepository(db),
        UserRepository(db),
        audit or MagicMock(),
        settings,
        oauth,
    )


def connect(service: GmailConnectService, user) -> EmailProfile:
    service.build_auth_url(user.id)
    return service.handle_callback("code-1", service.oauth.states[-1])


class TestConnect:
    def test_connected_account_becomes_the_active_own_account(
        self, db, settings, admin, primary
    ):
        audit = MagicMock()
        service = make(db, settings, FakeOAuth(), audit)

        connect(service, admin)

        own = EmailProfileRepository(db).get_own_account()
        assert own is not None
        assert own.provider == "gmail"
        assert own.username == own.from_email == "escritorio@gmail.com"
        assert own.last_test_ok is True
        assert own.version == 2
        # Token guardado criptografado, nunca em texto puro.
        assert own.secret_encrypted != "refresh-1"
        assert decrypt_secret(own, settings) == "refresh-1"
        audit.log_email_settings_updated.assert_called_once()

    def test_sending_uses_the_gmail_api_config(self, db, settings, admin, primary):
        connect(make(db, settings, FakeOAuth()), admin)

        own = EmailProfileRepository(db).get_own_account()
        config = profile_to_config(own, settings)

        assert isinstance(config, GmailConfig)
        assert config.refresh_token == "refresh-1"
        assert config.from_email == "escritorio@gmail.com"

    def test_creates_the_primary_profile_when_missing(self, db, settings, admin):
        connect(make(db, settings, FakeOAuth()), admin)

        assert EmailProfileRepository(db).get_own_account().provider == "gmail"

    def test_without_send_permission_nothing_is_saved(
        self, db, settings, admin, primary
    ):
        oauth = FakeOAuth(
            SimpleNamespace(
                refresh_token="refresh-1",
                id_token=id_token(),
                scopes=GMAIL_SCOPES,
                granted_scopes=[
                    "openid",
                    "https://www.googleapis.com/auth/userinfo.email",
                ],
            )
        )
        service = make(db, settings, oauth)

        with pytest.raises(GmailConnectError) as error:
            connect(service, admin)

        assert error.value.reason == "permission"
        assert EmailProfileRepository(db).get_own_account() is None

    def test_scope_change_warning_means_permission_denied(
        self, db, settings, admin, primary
    ):
        service = make(db, settings, FakeOAuth(error=Warning("Scope has changed")))

        with pytest.raises(GmailConnectError) as error:
            connect(service, admin)

        assert error.value.reason == "permission"

    def test_unverified_email_is_refused(self, db, settings, admin, primary):
        oauth = FakeOAuth(
            SimpleNamespace(
                refresh_token="refresh-1",
                id_token=id_token(verified=False),
                scopes=GMAIL_SCOPES,
                granted_scopes=GMAIL_SCOPES,
            )
        )

        with pytest.raises(GmailConnectError):
            connect(make(db, settings, oauth), admin)

    def test_only_admins_can_connect(self, db, settings, collaborator, primary):
        with pytest.raises(GmailConnectError):
            connect(make(db, settings, FakeOAuth()), collaborator)

    def test_forged_state_is_refused(self, db, settings, admin, primary):
        service = make(db, settings, FakeOAuth())
        forged = jwt.encode(
            {"sub": str(admin.id), "purpose": "gmail"}, "other", algorithm="HS256"
        )

        with pytest.raises(GmailConnectError):
            service.handle_callback("code-1", forged)

    def test_login_token_is_not_accepted_as_state(self, db, settings, admin, primary):
        service = make(db, settings, FakeOAuth())
        login = jwt.encode(
            {"sub": str(admin.id)}, settings.jwt_secret_key, algorithm="HS256"
        )

        with pytest.raises(GmailConnectError):
            service.handle_callback("code-1", login)

    def test_exchange_failure_is_reported(self, db, settings, admin, primary):
        service = make(db, settings, FakeOAuth(error=RuntimeError("boom")))

        with pytest.raises(GmailConnectError) as error:
            connect(service, admin)

        assert error.value.reason == "error"

    def test_not_configured_server_has_no_auth_url(self, db, settings, admin):
        service = make(db, settings, oauth=None)

        assert service.available is False
        with pytest.raises(GmailNotConfiguredError):
            service.build_auth_url(admin.id)

    def test_builder_requires_google_credentials(self, db, settings, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "")
        service = build_gmail_connect_service(
            EmailProfileRepository(db), UserRepository(db), MagicMock(), settings
        )
        assert service.available is False

        monkeypatch.setattr(settings, "google_client_id", "id")
        monkeypatch.setattr(settings, "google_client_secret", "secret")
        service = build_gmail_connect_service(
            EmailProfileRepository(db), UserRepository(db), MagicMock(), settings
        )
        assert service.available is True
        url = service.build_auth_url(1)
        assert "gmail.send" in url
        assert "access_type=offline" in url


class TestDisconnect:
    def test_goes_back_to_the_system_account_and_revokes(
        self, db, settings, admin, primary, revoked
    ):
        service = make(db, settings, FakeOAuth())
        connect(service, admin)

        service.disconnect(admin)

        assert EmailProfileRepository(db).get_own_account() is None
        profile = EmailProfileRepository(db).get_primary()
        assert profile.provider == "smtp"
        assert profile.secret_encrypted is None
        assert revoked == ["refresh-1"]

    def test_smtp_account_is_left_alone(self, db, settings, admin, primary, revoked):
        make(db, settings, FakeOAuth()).disconnect(admin)

        assert EmailProfileRepository(db).get_primary().provider == "smtp"
        assert revoked == []


class TestSwitchToSmtp:
    def test_google_token_is_never_used_as_smtp_password(
        self, db, settings, admin, primary
    ):
        connect(make(db, settings, FakeOAuth()), admin)
        profile = EmailProfileRepository(db).get_primary()
        service = EmailSettingsService(
            repository=EmailProfileRepository(db),
            tester=MagicMock(),
            audit=MagicMock(),
            renderer=EmailRenderer(StaticBrandingProvider()),
            settings=settings,
        )

        service.update_profile(
            profile.id,
            EmailProfileUpdate(
                preset="gmail",
                username="escritorio@gmail.com",
                is_active=False,
                version=profile.version,
            ),
            admin,
        )

        updated = EmailProfileRepository(db).get_primary()
        assert updated.provider == "smtp"
        assert updated.secret_encrypted is None


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("Gmail 401: o acesso à conta Google foi revogado", "revogado"),
        ("Gmail 429: busy", "limitou"),
        ("Gmail 400: Invalid To header", "recusou"),
        ("Gmail 503: backend", "Não foi possível"),
    ],
)
def test_gmail_errors_are_explained(reason, expected):
    assert expected in explain_gmail_error(reason).message
