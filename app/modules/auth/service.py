from datetime import timedelta

import bcrypt

from app.config.settings import get_settings
from app.modules.auth.schema import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
)
from app.modules.email.sender import TemplateSender
from app.modules.users.repository import UserRepository
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import (
    ExpiredResetTokenError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidResetTokenError,
    InviteNotAcceptedError,
)
from app.shared.security.one_time_token import OneTimeTokenService
from app.shared.security.password import hash_password, issue_access_token
from app.shared.types import UserStatus

settings = get_settings()


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        email_sender: TemplateSender,
        tokens: OneTimeTokenService | None = None,
    ) -> None:
        self.user_repository = user_repository
        self.email_sender = email_sender
        self.tokens = tokens or OneTimeTokenService()

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.user_repository.get_by_email(payload.email)

        if user is None:
            raise InvalidCredentialsError()

        if user.status == UserStatus.INVITED or not user.hashed_password:
            raise InviteNotAcceptedError()

        password_matches = bcrypt.checkpw(
            payload.password.encode("utf-8"),
            user.hashed_password.encode("utf-8"),
        )
        if not password_matches:
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        return TokenResponse(access_token=issue_access_token(user))

    def request_reset(self, payload: PasswordResetRequest) -> None:
        user = self.user_repository.get_by_email(payload.email)
        # Convidado ainda não tem senha: o caminho dele é o link do convite.
        if user is None or not user.is_active or user.status == UserStatus.INVITED:
            return

        token, token_hash = self.tokens.generate()
        expires_at = self.tokens.expires_at(
            timedelta(minutes=settings.password_reset_expire_minutes)
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
        self.email_sender.send(
            "password_reset",
            {
                "user_name": user.name,
                "reset_link": reset_link,
                "expire_minutes": settings.password_reset_expire_minutes,
            },
            to=user.email,
        )

    def confirm_reset(self, payload: PasswordResetConfirm) -> None:
        token_hash = self.tokens.hash(payload.token)
        user = self.user_repository.get_by_reset_token_hash(token_hash)

        if user is None:
            raise InvalidResetTokenError()

        if self.tokens.is_expired(user.reset_token_expires_at):
            raise ExpiredResetTokenError()

        with unit_of_work(self.user_repository.db):
            self.user_repository.update(
                user,
                {
                    "hashed_password": hash_password(payload.new_password),
                    "reset_token_hash": None,  # nosec B105
                    "reset_token_expires_at": None,  # nosec B105
                },
            )
