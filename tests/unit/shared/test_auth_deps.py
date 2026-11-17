from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.modules.permissions.model import Permission
from app.modules.users.model import User
from app.shared.deps.auth import (
    get_current_user,
    require_admin,
    require_any_permission,
    require_permission,
)
from app.shared.exceptions import ForbiddenError, UnauthorizedError
from app.shared.types import PermissionKey, Role


def make_credentials(token: str) -> MagicMock:
    creds = MagicMock()
    creds.credentials = token
    return creds


def make_user(**kwargs) -> User:
    defaults = {"id": 1, "role": Role.USER, "is_active": True, "permissions": []}
    defaults.update(kwargs)
    user = MagicMock(spec=User)
    for key, value in defaults.items():
        setattr(user, key, value)
    return user


def make_valid_token(user_id: int = 1, role: str = "USER") -> str:
    from app.config.settings import get_settings

    settings = get_settings()
    return jwt.encode(
        {"sub": str(user_id), "role": role},
        settings.jwt_secret_key,
        algorithm="HS256",
    )


@pytest.fixture
def db():
    return MagicMock()


class TestGetCurrentUser:
    def test_raises_on_invalid_signature(self, db):
        token = jwt.encode({"sub": "1"}, "wrong-secret", algorithm="HS256")

        with pytest.raises(UnauthorizedError):
            get_current_user(make_credentials(token), db)

    def test_raises_on_malformed_token(self, db):
        with pytest.raises(UnauthorizedError):
            get_current_user(make_credentials("not.a.token"), db)

    def test_raises_on_empty_token(self, db):
        with pytest.raises(UnauthorizedError):
            get_current_user(make_credentials(""), db)

    def test_raises_when_sub_missing(self, db):
        from app.config.settings import get_settings

        settings = get_settings()
        token = jwt.encode({"role": "USER"}, settings.jwt_secret_key, algorithm="HS256")

        with pytest.raises(UnauthorizedError):
            get_current_user(make_credentials(token), db)

    def test_raises_when_user_not_found(self, db):
        token = make_valid_token(user_id=99)

        with patch("app.shared.deps.auth.UserRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id.return_value = None

            with pytest.raises(UnauthorizedError):
                get_current_user(make_credentials(token), db)

    def test_raises_when_user_inactive(self, db):
        token = make_valid_token(user_id=1)

        with patch("app.shared.deps.auth.UserRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id.return_value = make_user(
                is_active=False
            )

            with pytest.raises(UnauthorizedError):
                get_current_user(make_credentials(token), db)

    def test_returns_user_when_valid(self, db):
        token = make_valid_token(user_id=1)
        user = make_user(id=1)

        with patch("app.shared.deps.auth.UserRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id.return_value = user

            result = get_current_user(make_credentials(token), db)

            assert result is user

    def test_looks_up_correct_user_id(self, db):
        token = make_valid_token(user_id=42)

        with patch("app.shared.deps.auth.UserRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id.return_value = make_user(id=42)

            get_current_user(make_credentials(token), db)

            mock_repo_cls.return_value.get_by_id.assert_called_once_with(42)


class TestRequireAdmin:
    def test_raises_when_role_is_user(self):
        with pytest.raises(ForbiddenError):
            require_admin(make_user(role=Role.USER))

    def test_returns_user_when_role_is_admin(self):
        admin = make_user(role=Role.ADMIN)

        result = require_admin(admin)

        assert result is admin


class TestRequirePermission:
    def test_admin_bypasses_permissions(self):
        admin = make_user(role=Role.ADMIN)
        assert require_permission(PermissionKey.PAGAMENTOS)(admin) is admin

    def test_user_with_key_passes(self):
        user = make_user(permissions=[Permission(key="pagamentos")])
        assert require_permission(PermissionKey.PAGAMENTOS)(user) is user

    def test_user_without_key_gets_forbidden(self):
        user = make_user(permissions=[Permission(key="artigos")])
        with pytest.raises(ForbiddenError):
            require_permission(PermissionKey.PAGAMENTOS)(user)


class TestRequireAnyPermission:
    def test_admin_bypasses_permissions(self):
        admin = make_user(role=Role.ADMIN)
        assert (
            require_any_permission(PermissionKey.CLIENTES, PermissionKey.PROCESSOS)(
                admin
            )
            is admin
        )

    def test_user_with_one_of_keys_passes(self):
        user = make_user(permissions=[Permission(key="processos")])
        assert (
            require_any_permission(PermissionKey.CLIENTES, PermissionKey.PROCESSOS)(
                user
            )
            is user
        )

    def test_user_without_any_key_gets_forbidden(self):
        user = make_user(permissions=[Permission(key="artigos")])
        with pytest.raises(ForbiddenError):
            require_any_permission(PermissionKey.CLIENTES, PermissionKey.PROCESSOS)(
                user
            )

    def test_requires_at_least_one_key(self):
        with pytest.raises(ValueError):
            require_any_permission()
