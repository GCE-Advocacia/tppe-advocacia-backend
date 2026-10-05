import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config.settings import get_settings
from app.modules.auth.schema import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
)
from app.modules.email.protocol import EmailService
from app.modules.users.repository import UserRepository
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import (
    ExpiredResetTokenError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidResetTokenError,
)

settings = get_settings()


class AuthService:
    def __init__(self, user_repository: UserRepository, email: EmailService) -> None:
        self.user_repository = user_repository
        self.email = email

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.user_repository.get_by_email(payload.email)

        if user is None:
            raise InvalidCredentialsError()

        password_matches = bcrypt.checkpw(
            payload.password.encode("utf-8"),
            user.hashed_password.encode("utf-8"),
        )
        if not password_matches:
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_expire_minutes
        )
        token_data = {
            "sub": str(user.id),
            "role": user.role.value,
            "can_view_payments": user.can_view_payments,
            "exp": expire,
        }
        token = jwt.encode(token_data, settings.jwt_secret_key, algorithm="HS256")

        return TokenResponse(access_token=token)

    def request_reset(self, payload: PasswordResetRequest) -> None:
        user = self.user_repository.get_by_email(payload.email)
        if user is None or not user.is_active:
            return

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.password_reset_expire_minutes
        )
        with unit_of_work(self.user_repository.db):
            self.user_repository.update(
                user,
                {
                    "reset_token_hash": token_hash,
                    "reset_token_expires_at": expires_at,
                },
            )

        reset_link = f"{settings.frontend_url}/reset-password?token={token}"
        self.email.send(
            to=user.email,
            subject="Redefinição de senha",
            html=(
                f"<p>Clique no link para redefinir sua senha "
                f"(válido por {settings.password_reset_expire_minutes} minutos):</p>"
                f"<p><a href='{reset_link}'>{reset_link}</a></p>"
            ),
        )

    def confirm_reset(self, payload: PasswordResetConfirm) -> None:
        token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
        user = self.user_repository.get_by_reset_token_hash(token_hash)

        if user is None:
            raise InvalidResetTokenError()

        expires_at = user.reset_token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise ExpiredResetTokenError()

        new_hashed = bcrypt.hashpw(
            payload.new_password.encode(), bcrypt.gensalt()
        ).decode()
        with unit_of_work(self.user_repository.db):
            self.user_repository.update(
                user,
                {
                    "hashed_password": new_hashed,
                    "reset_token_hash": None,  # nosec B105
                    "reset_token_expires_at": None,  # nosec B105
                },
            )
