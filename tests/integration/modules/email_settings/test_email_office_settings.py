from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.config.settings import get_settings
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.errors import EmailSendError
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer
from app.modules.email_outbox.model import (
    BreakerState,
    EmailAttempt,
    EmailOutboxItem,
    EmailProviderHealth,
    EmailStatus,
)
from app.modules.email_settings.model import EmailIdentity, EmailProfile
from app.modules.email_settings.repository import EmailProfileRepository
from app.modules.email_settings.schema import EmailIdentityUpdate
from app.modules.email_settings.service import EmailSettingsService
from app.modules.users.repository import UserRepository
from app.shared.exceptions import (
    EmailProfileNotFoundError,
    EmailProfileVersionConflictError,
    EmailTestSendFailedError,
)
from app.shared.types import Role

NOW = datetime.now(timezone.utc)


class Named(FakeEmailService):
    def __init__(self, name: str, fail_with: EmailSendError | None = None) -> None:
        super().__init__(fail_with)
        self.name = name


@pytest.fixture
def admin(db):
    user = UserRepository(db).create(
        name="Dra. Ana", email="ana@escritorio.com.br", hashed_password="x", role=Role.ADMIN
    )
    db.commit()
    return user


@pytest.fixture
def profiles(db):
    db.add_all(
        [
            EmailProfile(name="Primário", priority=1, provider="smtp", security="starttls"),
            EmailProfile(name="Reserva", priority=2, provider="smtp", security="starttls"),
        ]
    )
    db.add(EmailIdentity(id=1, version=1))
    db.commit()


@pytest.fixture
def audit():
    return MagicMock()


def make_service(db, audit, chain=None):
    return EmailSettingsService(
        repository=EmailProfileRepository(db),
        tester=MagicMock(),
        audit=audit,
        renderer=EmailRenderer(StaticBrandingProvider()),
        settings=get_settings(),
        email_service=(lambda: chain) if chain is not None else None,
    )


def activate_own(db, preset="gmail"):
    own = db.query(EmailProfile).filter_by(priority=1).one()
    own.is_active = True
    own.preset = preset
    own.host, own.port = "smtp.gmail.com", 587
    own.username = own.from_email = "escritorio@gmail.com"
    own.last_test_ok = True
    db.commit()
    return own


class TestIdentity:
    def test_saves_name_and_reply_to_with_audit(self, db, profiles, admin, audit):
        service = make_service(db, audit)

        identity = service.update_identity(
            EmailIdentityUpdate(
                from_name="Souza & Lima", reply_to="contato@souzalima.adv.br", version=1
            ),
            admin,
        )

        assert identity.from_name == "Souza & Lima"
        assert identity.version == 2
        audit.log_email_settings_updated.assert_called_once()
        assert audit.log_email_settings_updated.call_args.args[0] == "Identidade"

    def test_stale_version_conflicts(self, db, profiles, admin, audit):
        service = make_service(db, audit)
        service.update_identity(EmailIdentityUpdate(from_name="A", version=1), admin)

        with pytest.raises(EmailProfileVersionConflictError):
            service.update_identity(EmailIdentityUpdate(from_name="B", version=1), admin)


class TestProfiles:
    def test_only_own_account_is_listed(self, db, profiles, audit):
        assert [p.priority for p in make_service(db, audit).list_profiles()] == [1]

    def test_old_fallback_is_hidden(self, db, profiles, audit):
        fallback = db.query(EmailProfile).filter_by(priority=2).one()

        with pytest.raises(EmailProfileNotFoundError):
            make_service(db, audit)._get(fallback.id)


class TestStatus:
    def test_without_own_account_uses_system(self, db, profiles, audit):
        status = make_service(db, audit).status()

        assert status.state == "ok"
        assert status.account == "system"
        assert status.own_account_configured is False

    def test_own_account_in_use(self, db, profiles, audit):
        activate_own(db)

        status = make_service(db, audit).status()

        assert status.account == "own"
        assert status.account_email == "escritorio@gmail.com"

    def test_own_account_with_open_circuit_is_degraded_and_uses_system(
        self, db, profiles, audit
    ):
        activate_own(db)
        db.add(
            EmailProviderHealth(
                provider="own", state=BreakerState.OPEN, consecutive_failures=5
            )
        )
        db.commit()

        status = make_service(db, audit).status()

        assert status.state == "degraded"
        assert status.account == "system"
        assert "conta do sistema" in status.own_account_error

    def test_last_sent_comes_from_history(self, db, profiles, audit):
        db.add(
            EmailOutboxItem(
                id="x1", template_id="test", context={}, to=["a@b.com"], cc=[], bcc=[],
                status=EmailStatus.SENT, attempts=1, next_attempt_at=NOW,
                created_at=NOW, sent_at=NOW,
            )
        )
        db.commit()

        status = make_service(db, audit).status()

        assert status.last_sent_at is not None

    def test_only_failures_in_last_hour_is_down(self, db, profiles, audit):
        db.add(
            EmailOutboxItem(
                id="x2", template_id="test", context={}, to=["a@b.com"], cc=[], bcc=[],
                status=EmailStatus.FAILED, attempts=1, next_attempt_at=NOW,
                created_at=NOW,
            )
        )
        db.add(
            EmailAttempt(
                email_id="x2", attempt=1, provider="system", success=False,
                error="timeout", created_at=NOW - timedelta(minutes=5),
            )
        )
        db.commit()

        assert make_service(db, audit).status().state == "down"


class TestSendMe:
    def test_sends_only_to_the_logged_admin(self, db, profiles, admin, audit):
        system = Named("system")
        service = make_service(db, audit, FailoverEmailService([system]))

        result = service.test_send_me(admin)

        assert [m.to for m in system.messages] == [["ana@escritorio.com.br"]]
        assert result.account == "system"
        identity = db.get(EmailIdentity, 1)
        assert identity.last_test_ok is True

    def test_own_account_failure_falls_back_to_system(self, db, profiles, admin, audit):
        activate_own(db)
        own = Named(
            "own",
            EmailSendError("timed out", transient=True, failover=True, provider="own"),
        )
        system = Named("system")
        service = make_service(db, audit, FailoverEmailService([own, system]))

        result = service.test_send_me(admin)

        assert result.account == "system"
        assert result.fallback_used is True
        assert len(system.messages) == 1

    def test_failure_is_explained_and_recorded(self, db, profiles, admin, audit):
        activate_own(db)
        failing = Named(
            "own",
            EmailSendError(
                "Autenticação recusada: 535 bad", transient=False, failover=False,
                provider="own", smtp_code=535,
            ),
        )
        service = make_service(db, audit, FailoverEmailService([failing]))

        with pytest.raises(EmailTestSendFailedError) as exc:
            service.test_send_me(admin)

        assert "senha de app" in exc.value.message
        identity = db.get(EmailIdentity, 1)
        assert identity.last_test_ok is False
        assert identity.last_test_error == "O e-mail ou a senha não foram aceitos."
