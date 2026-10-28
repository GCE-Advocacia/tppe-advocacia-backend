from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.config.settings import get_settings
from app.modules.email.errors import EmailSendError
from app.modules.email.fake_service import FakeEmailService
from app.modules.users.invite_service import InviteService
from app.modules.users.model import User
from app.modules.users.schema import UserCreate, UserUpdate
from app.modules.users.service import UserService
from app.shared.exceptions import EmailAlreadyExistsError, UserNotFoundError
from app.shared.security.one_time_token import OneTimeTokenService
from app.shared.types import Role, UserStatus


def make_integrity_error() -> IntegrityError:
    return IntegrityError("stmt", "params", Exception("unique constraint"))


def make_user(**kwargs) -> User:
    now = datetime.now(UTC)
    defaults = {
        "id": 1,
        "name": "Test User",
        "email": "test@test.com",
        "hashed_password": "hashed",
        "role": Role.USER,
        "is_active": True,
        "can_view_payments": False,
        "created_by": None,
        "updated_by": None,
        "created_at": now,
        "updated_at": now,
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
def email():
    from app.modules.email.fake_service import FakeEmailService

    return FakeEmailService()


@pytest.fixture
def email_sender(email):
    from app.modules.email.branding import StaticBrandingProvider
    from app.modules.email.renderer import EmailRenderer
    from app.modules.email.sender import TemplatedEmailSender

    return TemplatedEmailSender(EmailRenderer(StaticBrandingProvider()), email)


@pytest.fixture
def audit():
    return MagicMock()


@pytest.fixture
def invite_repo():
    repo = MagicMock()
    repo.get_active_by_user.return_value = None
    return repo


@pytest.fixture
def invites(invite_repo, repo, email_sender):
    return InviteService(invite_repo, repo, email_sender, get_settings())


@pytest.fixture
def service(repo, invites, audit):
    return UserService(repo, invites, audit)


class TestListUsers:
    def test_calls_repo_with_correct_params(self, service, repo):
        repo.get_all.return_value = ([], 0)

        service.list_users(role=Role.USER, is_active=True, page=2, limit=10)

        repo.get_all.assert_called_once_with(
            role=Role.USER, is_active=True, page=2, limit=10
        )

    def test_returns_user_read_list(self, service, repo):
        users = [make_user(id=1), make_user(id=2, email="other@test.com")]
        repo.get_all.return_value = (users, 2)

        result, total = service.list_users(role=None, is_active=None, page=1, limit=20)

        assert len(result) == 2
        assert total == 2
        assert result[0].id == 1
        assert result[1].id == 2

    def test_returns_empty_list_when_no_users(self, service, repo):
        repo.get_all.return_value = ([], 0)

        result, total = service.list_users(role=None, is_active=None, page=1, limit=20)

        assert result == []
        assert total == 0

    def test_passes_none_filters_to_repo(self, service, repo):
        repo.get_all.return_value = ([], 0)

        service.list_users(role=None, is_active=None, page=1, limit=20)

        repo.get_all.assert_called_once_with(
            role=None, is_active=None, page=1, limit=20
        )


class TestGetUser:
    def test_returns_user_read_when_found(self, service, repo):
        repo.get_by_id.return_value = make_user(id=5, name="Alice")

        result = service.get_user(5)

        assert result.id == 5
        assert result.name == "Alice"

    def test_raises_user_not_found_when_missing(self, service, repo):
        repo.get_by_id.return_value = None

        with pytest.raises(UserNotFoundError):
            service.get_user(999)

    def test_calls_repo_with_correct_id(self, service, repo):
        repo.get_by_id.return_value = make_user(id=7)

        service.get_user(7)

        repo.get_by_id.assert_called_once_with(7)


class TestCreateUser:
    def test_raises_when_email_already_exists(self, service, repo):
        repo.create.side_effect = make_integrity_error()

        with pytest.raises(EmailAlreadyExistsError):
            service.create_user(
                UserCreate(name="Alice", email="alice@test.com"),
                created_by=make_user(id=1),
            )

    def test_does_not_send_email_when_integrity_error(self, service, repo, email):
        repo.create.side_effect = make_integrity_error()

        with pytest.raises(EmailAlreadyExistsError):
            service.create_user(
                UserCreate(name="Alice", email="alice@test.com"),
                created_by=make_user(id=1),
            )

        assert email.sent == []

    def test_creates_invited_user_without_password(self, service, repo):
        repo.create.return_value = make_user()

        service.create_user(
            UserCreate(name="Alice", email="alice@test.com"), created_by=make_user(id=1)
        )

        kwargs = repo.create.call_args.kwargs
        assert kwargs["hashed_password"] is None
        assert kwargs["status"] == UserStatus.INVITED

    def test_creates_invite_with_hashed_token(self, service, repo, invite_repo):
        repo.create.return_value = make_user(id=10)

        service.create_user(
            UserCreate(name="Alice", email="alice@test.com"), created_by=make_user(id=1)
        )

        kwargs = invite_repo.create.call_args.kwargs
        assert kwargs["user_id"] == 10
        assert kwargs["created_by"] == 1
        assert len(kwargs["token_hash"]) == 64

    def test_sends_invite_link_without_password(
        self, service, repo, email, invite_repo
    ):
        repo.create.return_value = make_user(email="alice@test.com")

        service.create_user(
            UserCreate(name="Alice", email="alice@test.com"), created_by=make_user(id=1)
        )

        assert len(email.messages) == 1
        message = email.messages[0]
        assert message.to == ["alice@test.com"]
        assert "senha" not in message.subject.lower()
        assert "senha temporária" not in message.text.lower()
        # O link leva o token cujo hash foi gravado no banco.
        token = message.text.split("/convite/")[1].split()[0]
        token_hash = invite_repo.create.call_args.kwargs["token_hash"]
        assert OneTimeTokenService.hash(token) == token_hash

    def test_email_failure_does_not_block_creation(self, service, repo, invites, audit):
        invites.email_sender.email_service = FakeEmailService(
            fail_with=EmailSendError(
                "down", transient=True, failover=True, provider="smtp"
            )
        )
        repo.create.return_value = make_user(id=10)

        user = service.create_user(
            UserCreate(name="Alice", email="alice@test.com"), created_by=make_user(id=1)
        )

        assert user.id == 10
        audit.log_user_created.assert_called_once()

    def test_always_assigns_role_user(self, service, repo):
        repo.create.return_value = make_user()

        service.create_user(
            UserCreate(name="Alice", email="alice@test.com"), created_by=make_user(id=1)
        )

        assert repo.create.call_args.kwargs["role"] == Role.USER

    def test_passes_name_and_email_to_repo(self, service, repo):
        repo.create.return_value = make_user()

        service.create_user(
            UserCreate(name="Bob", email="bob@test.com"), created_by=make_user(id=1)
        )

        kwargs = repo.create.call_args.kwargs
        assert kwargs["name"] == "Bob"
        assert kwargs["email"] == "bob@test.com"

    def test_returns_user_read_on_success(self, service, repo):
        repo.create.return_value = make_user(
            id=10, name="Alice", email="alice@test.com"
        )

        result = service.create_user(
            UserCreate(name="Alice", email="alice@test.com"), created_by=make_user(id=1)
        )

        assert result.id == 10
        assert result.name == "Alice"
        assert result.email == "alice@test.com"

    def test_logs_user_created_after_user_creation(self, service, repo, audit):
        user = make_user(id=10)
        repo.create.return_value = user
        admin = make_user(id=1, name="Admin")

        service.create_user(
            UserCreate(name="Alice", email="alice@test.com"), created_by=admin
        )

        audit.log_user_created.assert_called_once_with(user, admin)

    def test_does_not_log_when_email_already_exists(self, service, repo, audit):
        repo.create.side_effect = make_integrity_error()

        with pytest.raises(EmailAlreadyExistsError):
            service.create_user(
                UserCreate(name="Alice", email="alice@test.com"),
                created_by=make_user(id=1),
            )

        audit.log_user_created.assert_not_called()


class TestUpdateUser:
    def test_raises_user_not_found_when_missing(self, service, repo):
        repo.get_by_id.return_value = None

        with pytest.raises(UserNotFoundError):
            service.update_user(
                999, UserUpdate(name="New Name"), updated_by=make_user(id=1)
            )

    def test_does_not_call_repo_update_when_user_missing(self, service, repo):
        repo.get_by_id.return_value = None

        with pytest.raises(UserNotFoundError):
            service.update_user(
                999, UserUpdate(name="New Name"), updated_by=make_user(id=1)
            )

        repo.update.assert_not_called()

    def test_raises_email_already_exists_on_duplicate_email(self, service, repo):
        repo.get_by_id.return_value = make_user(email="original@test.com")
        repo.email_exists.return_value = True

        with pytest.raises(EmailAlreadyExistsError):
            service.update_user(
                1, UserUpdate(email="taken@test.com"), updated_by=make_user(id=1)
            )

    def test_does_not_check_email_conflict_when_email_unchanged(self, service, repo):
        existing = make_user(email="same@test.com")
        repo.get_by_id.return_value = existing
        repo.update.return_value = existing

        service.update_user(
            1, UserUpdate(email="same@test.com"), updated_by=make_user(id=1)
        )

        repo.email_exists.assert_not_called()

    def test_returns_updated_user_read(self, service, repo):
        repo.get_by_id.return_value = make_user(id=1, name="Old")
        repo.update.return_value = make_user(id=1, name="New")

        result = service.update_user(
            1, UserUpdate(name="New"), updated_by=make_user(id=1)
        )

        assert result.name == "New"

    def test_passes_only_non_none_fields_to_repo(self, service, repo):
        existing = make_user()
        repo.get_by_id.return_value = existing
        repo.update.return_value = existing

        service.update_user(1, UserUpdate(name="Updated"), updated_by=make_user(id=1))

        updates = repo.update.call_args[0][1]
        assert "name" in updates
        assert "email" not in updates
        assert "role" not in updates
        assert "is_active" not in updates

    def test_can_deactivate_user(self, service, repo):
        repo.get_by_id.return_value = make_user(is_active=True)
        repo.update.return_value = make_user(is_active=False)

        result = service.update_user(
            1, UserUpdate(is_active=False), updated_by=make_user(id=1)
        )

        assert result.is_active is False

    def test_can_promote_to_admin(self, service, repo):
        repo.get_by_id.return_value = make_user(role=Role.USER)
        repo.update.return_value = make_user(role=Role.ADMIN)

        result = service.update_user(
            1, UserUpdate(role=Role.ADMIN), updated_by=make_user(id=1)
        )

        assert result.role == Role.ADMIN

    def test_email_conflict_check_excludes_own_id(self, service, repo):
        existing = make_user(id=1, email="original@test.com")
        repo.get_by_id.return_value = existing
        repo.email_exists.return_value = False
        repo.update.return_value = existing

        service.update_user(
            1, UserUpdate(email="new@test.com"), updated_by=make_user(id=1)
        )

        repo.email_exists.assert_called_once_with("new@test.com", exclude_id=1)

    def test_logs_user_deactivated_when_active_user_is_deactivated(
        self, service, repo, audit
    ):
        repo.get_by_id.return_value = make_user(is_active=True)
        updated = make_user(is_active=False)
        repo.update.return_value = updated
        admin = make_user(id=5, name="Admin")

        service.update_user(1, UserUpdate(is_active=False), updated_by=admin)

        audit.log_user_deactivated.assert_called_once_with(updated, admin)

    def test_does_not_log_when_user_already_inactive(self, service, repo, audit):
        repo.get_by_id.return_value = make_user(is_active=False)
        repo.update.return_value = make_user(is_active=False)

        service.update_user(1, UserUpdate(is_active=False), updated_by=make_user(id=5))

        audit.log_user_deactivated.assert_not_called()

    def test_does_not_log_when_only_name_updated(self, service, repo, audit):
        existing = make_user(is_active=True)
        repo.get_by_id.return_value = existing
        repo.update.return_value = existing

        service.update_user(1, UserUpdate(name="New Name"), updated_by=make_user(id=5))

        audit.log_user_deactivated.assert_not_called()

    def test_logs_user_updated_when_name_changes(self, service, repo, audit):
        existing = make_user(is_active=True)
        updated = make_user(name="New Name")
        repo.get_by_id.return_value = existing
        repo.update.return_value = updated
        admin = make_user(id=5)

        service.update_user(1, UserUpdate(name="New Name"), updated_by=admin)

        audit.log_user_updated.assert_called_once_with(updated, admin)

    def test_logs_user_updated_when_role_changes(self, service, repo, audit):
        existing = make_user(role=Role.USER)
        updated = make_user(role=Role.ADMIN)
        repo.get_by_id.return_value = existing
        repo.update.return_value = updated
        admin = make_user(id=5)

        service.update_user(1, UserUpdate(role=Role.ADMIN), updated_by=admin)

        audit.log_user_updated.assert_called_once_with(updated, admin)

    def test_does_not_log_user_updated_when_deactivating(self, service, repo, audit):
        repo.get_by_id.return_value = make_user(is_active=True)
        repo.update.return_value = make_user(is_active=False)
        admin = make_user(id=5)

        service.update_user(1, UserUpdate(is_active=False), updated_by=admin)

        audit.log_user_updated.assert_not_called()

    def test_logs_user_updated_when_activating(self, service, repo, audit):
        existing = make_user(is_active=False)
        updated = make_user(is_active=True)
        repo.get_by_id.return_value = existing
        repo.update.return_value = updated
        admin = make_user(id=5)

        service.update_user(1, UserUpdate(is_active=True), updated_by=admin)

        audit.log_user_updated.assert_called_once_with(updated, admin)

    def test_passes_can_view_payments_to_repo(self, service, repo):
        existing = make_user(can_view_payments=False)
        repo.get_by_id.return_value = existing
        repo.update.return_value = make_user(can_view_payments=True)

        result = service.update_user(
            1, UserUpdate(can_view_payments=True), updated_by=make_user(id=5)
        )

        updates = repo.update.call_args[0][1]
        assert updates["can_view_payments"] is True
        assert result.can_view_payments is True

    def test_logs_user_updated_when_can_view_payments_changes(
        self, service, repo, audit
    ):
        existing = make_user(can_view_payments=True)
        updated = make_user(can_view_payments=False)
        repo.get_by_id.return_value = existing
        repo.update.return_value = updated
        admin = make_user(id=5)

        service.update_user(1, UserUpdate(can_view_payments=False), updated_by=admin)

        audit.log_user_updated.assert_called_once_with(updated, admin)
        audit.log_user_deactivated.assert_not_called()
