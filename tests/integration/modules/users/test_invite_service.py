from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import get_settings
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer
from app.modules.email.sender import TemplatedEmailSender
from app.modules.users.invite_model import UserInvite
from app.modules.users.invite_repository import InviteRepository
from app.modules.users.invite_service import InviteService, invite_status
from app.modules.users.repository import UserRepository
from app.shared.exceptions import (
    ExpiredInviteError,
    InvalidInviteError,
    InviteAlreadyUsedError,
    InviteResendLimitError,
    UserNotInvitedError,
)
from app.shared.security.one_time_token import OneTimeTokenService
from app.shared.types import Role, UserStatus


@pytest.fixture
def email():
    return FakeEmailService()


@pytest.fixture
def service(db, email):
    sender = TemplatedEmailSender(EmailRenderer(StaticBrandingProvider()), email)
    return InviteService(
        InviteRepository(db), UserRepository(db), sender, get_settings()
    )


@pytest.fixture
def admin(db):
    user = UserRepository(db).create(
        name="Admin", email="admin@test.com", hashed_password="x", role=Role.ADMIN
    )
    db.commit()
    return user


@pytest.fixture
def invited(db, service, admin):
    user = UserRepository(db).create(
        name="Convidado",
        email="convidado@test.com",
        hashed_password=None,
        role=Role.USER,
        status=UserStatus.INVITED,
        created_by=admin.id,
    )
    issued = service.issue(user, admin)
    db.commit()
    return user, issued.token


def _token_from(email: FakeEmailService) -> str:
    return email.messages[-1].text.split("/convite/")[1].split()[0]


class TestAccept:
    def test_sets_password_activates_and_returns_jwt(self, db, service, invited):
        user, token = invited

        result = service.accept(token, "NovaSenha@123")

        db.refresh(user)
        assert result.access_token
        assert user.status == UserStatus.ACTIVE
        assert user.hashed_password and user.hashed_password != "NovaSenha@123"

    def test_token_used_twice_fails(self, service, invited):
        _, token = invited
        service.accept(token, "NovaSenha@123")

        with pytest.raises(InviteAlreadyUsedError):
            service.accept(token, "OutraSenha@123")

    def test_expired_token_fails(self, db, service, invited):
        user, token = invited
        invite = db.query(UserInvite).filter_by(user_id=user.id).one()
        invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

        with pytest.raises(ExpiredInviteError):
            service.accept(token, "NovaSenha@123")

    def test_unknown_token_is_generic(self, service, invited):
        with pytest.raises(InvalidInviteError):
            service.get_public("nao-existe")


class TestResend:
    def test_resend_invalidates_previous_link(self, service, invited, admin, email):
        user, old_token = invited

        service.resend(user.id, admin)
        new_token = _token_from(email)

        assert new_token != old_token
        # Cancelado responde igual a inexistente.
        with pytest.raises(InvalidInviteError):
            service.get_public(old_token)
        assert service.get_public(new_token).id == user.id

    def test_resend_limit_per_hour(self, service, invited, admin):
        user, _ = invited
        # O convite da criação já conta: com limite 3, sobram 2 reenvios.
        service.resend(user.id, admin)
        service.resend(user.id, admin)

        with pytest.raises(InviteResendLimitError):
            service.resend(user.id, admin)

    def test_resend_for_active_user_is_rejected(self, service, admin):
        with pytest.raises(UserNotInvitedError):
            service.resend(admin.id, admin)

    def test_cancel_marks_cancelled(self, db, service, invited, admin):
        user, token = invited

        service.cancel(user.id, admin)

        latest = service.latest_by_users([user.id])[user.id]
        assert invite_status(latest) == "CANCELLED"
        with pytest.raises(InvalidInviteError):
            service.get_public(token)


def test_invite_email_has_link_and_no_password(service, invited, admin, email):
    user, _ = invited

    service.resend(user.id, admin)

    message = email.messages[-1]
    token = _token_from(email)
    assert message.to == [user.email]
    assert f"/convite/{token}" in message.html
    assert "senha temporária" not in message.html.lower()
    stored = service.invites.get_active_by_user(user.id)
    assert stored.token_hash == OneTimeTokenService.hash(token)
    assert token not in stored.token_hash
