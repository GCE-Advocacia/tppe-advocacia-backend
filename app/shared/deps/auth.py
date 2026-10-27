from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.exceptions import ForbiddenError, UnauthorizedError
from app.shared.types import PermissionKey, Role

settings = get_settings()
_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret_key, algorithms=["HS256"]
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise UnauthorizedError()

    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError()

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != Role.ADMIN:
        raise ForbiddenError()
    return current_user


def require_any_permission(*keys: PermissionKey) -> Callable[..., User]:
    """Libera ADMIN ou o usuário que tenha ao menos uma das permissões.

    As permissões são relidas do banco a cada requisição (a sessão é nova por
    requisição), então revogar uma aba bloqueia o mesmo token na hora.
    """
    if not keys:
        raise ValueError("require_any_permission precisa de ao menos uma chave")
    allowed = frozenset(PermissionKey(key).value for key in keys)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role == Role.ADMIN:
            return current_user
        if allowed.isdisjoint(p.key for p in current_user.permissions):
            raise ForbiddenError()
        return current_user

    # Usado pelo teste que garante que nenhuma rota fica só com get_current_user.
    dependency.required_permissions = allowed
    return dependency


def require_permission(key: PermissionKey) -> Callable[..., User]:
    return require_any_permission(key)
