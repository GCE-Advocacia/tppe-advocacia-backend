from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import bcrypt
import jwt
import pytest

from app.modules.auth.schema import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
)
from app.modules.auth.service import AuthService
from app.modules.email.fake_service import FakeEmailService
from app.modules.users.model import User
from app.shared.exceptions import (
    ExpiredResetTokenError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidResetTokenError,
)
from app.shared.types import Role


def make_user(**kwargs) -> User:
    defaults = {
        "id": 1,
        "name": "Test User",
        "email": "test@test.com",
        "hashed_password": bcrypt.hashpw(
            b"correct_password", bcrypt.gensalt()
        ).decode(),
        "role": Role.USER,
        "is_active": True,
        "can_view_payments": False,
        "reset_token_hash": None,
        "reset_token_expires_at": None,
    }
    defaults.update(kwargs)
    user = MagicMock(spec=User)
    for key, value in defaults.items():
        setattr(user, key, value)
    return user


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def fake_email():
    return FakeEmailService()


@pytest.fixture
def service(repo, fake_email):
    return AuthService(repo, fake_email)


def make_login_payload(password="correct_password"):
    return LoginRequest(email="test@test.com", password=password)


class TestLogin:
    def test_raises_when_user_not_found(self, service, repo):
        repo.get_by_email.return_value = None

        with pytest.raises(InvalidCredentialsError):
            service.login(make_login_payload())

    def test_does_not_leak_not_found_vs_wrong_password(self, service, repo):
        repo.get_by_email.return_value = None

        with pytest.raises(InvalidCredentialsError):
            service.login(make_login_payload("wrong"))

    def test_raises_on_wrong_password(self, service, repo):
        repo.get_by_email.return_value = make_user()

        with pytest.raises(InvalidCredentialsError):
            service.login(make_login_payload("wrong_password"))

    def test_does_not_raise_on_correct_password(self, service, repo):
        repo.get_by_email.return_value = make_user()

        result = service.login(make_login_payload("correct_password"))

        assert result.access_token is not None

    def test_raises_when_user_inactive(self, service, repo):
        repo.get_by_email.return_value = make_user(is_active=False)

        with pytest.raises(InactiveUserError):
            service.login(make_login_payload())

    def test_inactive_check_happens_after_password_check(self, service, repo):
        repo.get_by_email.return_value = make_user(is_active=False)

        with pytest.raises(InactiveUserError):
            service.login(make_login_payload("correct_password"))

    def test_returns_token_response(self, service, repo):
        repo.get_by_email.return_value = make_user()

        result = service.login(make_login_payload())

        assert result.token_type == "bearer"
        assert isinstance(result.access_token, str)
        assert len(result.access_token) > 0

    def test_token_contains_user_id(self, service, repo):
        from app.config.settings import get_settings

        settings = get_settings()
        repo.get_by_email.return_value = make_user(id=42)

        result = service.login(make_login_payload())

        payload = jwt.decode(
            result.access_token, settings.jwt_secret_key, algorithms=["HS256"]
        )
        assert payload["sub"] == "42"

    def test_token_contains_role(self, service, repo):
        from app.config.settings import get_settings

        settings = get_settings()
        repo.get_by_email.return_value = make_user(role=Role.ADMIN)

        result = service.login(make_login_payload())

        payload = jwt.decode(
            result.access_token, settings.jwt_secret_key, algorithms=["HS256"]
        )
        assert payload["role"] == "ADMIN"

    def test_token_contains_can_view_payments(self, service, repo):
        from app.config.settings import get_settings

        settings = get_settings()
        repo.get_by_email.return_value = make_user(can_view_payments=True)

        result = service.login(make_login_payload())

        payload = jwt.decode(
            result.access_token, settings.jwt_secret_key, algorithms=["HS256"]
        )
        assert payload["can_view_payments"] is True

    def test_token_contains_expiry(self, service, repo):
        from app.config.settings import get_settings

        settings = get_settings()
        repo.get_by_email.return_value = make_user()

        result = service.login(make_login_payload())

        payload = jwt.decode(
            result.access_token, settings.jwt_secret_key, algorithms=["HS256"]
        )
        assert "exp" in payload


class TestRequestReset:
    def test_does_nothing_when_email_not_found(self, service, repo, fake_email):
        repo.get_by_email.return_value = None

        service.request_reset(PasswordResetRequest(email="unknown@test.com"))

        repo.update.assert_not_called()
        assert len(fake_email.sent) == 0

    def test_does_nothing_when_user_inactive(self, service, repo, fake_email):
        repo.get_by_email.return_value = make_user(is_active=False)

        service.request_reset(PasswordResetRequest(email="test@test.com"))

        repo.update.assert_not_called()
        assert len(fake_email.sent) == 0

    def test_stores_token_hash_for_active_user(self, service, repo, fake_email):
        repo.get_by_email.return_value = make_user()

        service.request_reset(PasswordResetRequest(email="test@test.com"))

        update_data = repo.update.call_args[0][1]
        assert update_data["reset_token_hash"] is not None
        assert len(update_data["reset_token_hash"]) == 64  # sha256 hex digest

    def test_stores_expiry_for_active_user(self, service, repo, fake_email):
        repo.get_by_email.return_value = make_user()

        service.request_reset(PasswordResetRequest(email="test@test.com"))

        update_data = repo.update.call_args[0][1]
        assert update_data["reset_token_expires_at"] > datetime.now(timezone.utc)

    def test_sends_email_to_user(self, service, repo, fake_email):
        repo.get_by_email.return_value = make_user(email="test@test.com")

        service.request_reset(PasswordResetRequest(email="test@test.com"))

        assert len(fake_email.sent) == 1
        assert fake_email.sent[0]["to"] == "test@test.com"

    def test_email_contains_reset_link(self, service, repo, fake_email):
        repo.get_by_email.return_value = make_user()

        service.request_reset(PasswordResetRequest(email="test@test.com"))

        assert "reset-password?token=" in fake_email.sent[0]["html"]


class TestConfirmReset:
    def _valid_expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(minutes=30)

    def _expired_at(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(minutes=1)

    def test_raises_when_token_not_found(self, service, repo):
        repo.get_by_reset_token_hash.return_value = None

        with pytest.raises(InvalidResetTokenError):
            service.confirm_reset(
                PasswordResetConfirm(token="invalid", new_password="newpass1")
            )

    def test_raises_when_token_expired(self, service, repo):
        repo.get_by_reset_token_hash.return_value = make_user(
            reset_token_hash="somehash",
            reset_token_expires_at=self._expired_at(),
        )

        with pytest.raises(ExpiredResetTokenError):
            service.confirm_reset(
                PasswordResetConfirm(token="sometoken", new_password="newpass1")
            )

    def test_updates_password_on_valid_token(self, service, repo):
        repo.get_by_reset_token_hash.return_value = make_user(
            reset_token_hash="somehash",
            reset_token_expires_at=self._valid_expires_at(),
        )

        service.confirm_reset(
            PasswordResetConfirm(token="sometoken", new_password="newpass123")
        )

        update_data = repo.update.call_args[0][1]
        assert "hashed_password" in update_data
        assert bcrypt.checkpw(b"newpass123", update_data["hashed_password"].encode())

    def test_clears_token_fields_after_confirm(self, service, repo):
        repo.get_by_reset_token_hash.return_value = make_user(
            reset_token_hash="somehash",
            reset_token_expires_at=self._valid_expires_at(),
        )

        service.confirm_reset(
            PasswordResetConfirm(token="sometoken", new_password="newpass123")
        )

        update_data = repo.update.call_args[0][1]
        assert update_data["reset_token_hash"] is None
        assert update_data["reset_token_expires_at"] is None
