import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config.settings import Settings
from app.modules.auth.schema import TokenResponse
from app.modules.email.errors import EmailSendError
from app.modules.email.sender import TemplatedEmailSender
from app.modules.users.invite_model import UserInvite
from app.modules.users.invite_repository import InviteRepository
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import (
    ExpiredInviteError,
    InvalidInviteError,
    InviteAlreadyUsedError,
    InviteNotFoundError,
    InviteResendLimitError,
    UserNotFoundError,
    UserNotInvitedError,
)
from app.shared.security.one_time_token import OneTimeTokenService
from app.shared.security.password import hash_password, issue_access_token
from app.shared.types import UserStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssuedInvite:
    token: str
    expires_at: datetime


def invite_status(invite: UserInvite | None, now: datetime | None = None) -> str | None:
    """``PENDING``, ``EXPIRED``, ``USED``, ``CANCELLED`` ou ``None`` (sem convite)."""
    if invite is None:
        return None
    if invite.used_at is not None:
        return "USED"
    if invite.revoked_at is not None:
        return "CANCELLED"
    if OneTimeTokenService.is_expired(invite.expires_at, now):
        return "EXPIRED"
    return "PENDING"


class InviteService:
    def __init__(
        self,
        invites: InviteRepository,
        users: UserRepository,
        email_sender: TemplatedEmailSender,
        settings: Settings,
        tokens: OneTimeTokenService | None = None,
    ) -> None:
        self.invites = invites
        self.users = users
        self.email_sender = email_sender
        self.settings = settings
        self.tokens = tokens or OneTimeTokenService()

    # ---- emissão (dentro da transação de quem chama) ---------------------

    def issue(self, user: User, created_by: User | None) -> IssuedInvite:
        """Revoga o convite ativo (se houver) e cria outro. Não comita:
        quem chama envolve em ``unit_of_work``. O token em texto só existe no
        retorno, para montar o link."""
        now = datetime.now(timezone.utc)
        active = self.invites.get_active_by_user(user.id)
        if active is not None:
            self.invites.update(active, {"revoked_at": now})
        token, token_hash = self.tokens.generate()
        expires_at = self.tokens.expires_at(
            timedelta(hours=self.settings.invite_expire_hours), now
        )
        self.invites.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_by=created_by.id if created_by else None,
        )
        return IssuedInvite(token=token, expires_at=expires_at)

    def invite_link(self, token: str) -> str:
        return f"{self.settings.frontend_url}/convite/{token}"

    def send_invite_email(
        self, user: User, issued: IssuedInvite, invited_by: str | None = None
    ) -> bool:
        """Envia fora da transação. Falha de e-mail não desfaz o convite: o
        admin vê o convite pendente e pode reenviar.

        TODO(outbox): trocar por ``EmailOutbox.enqueue`` (Pessoa 3) dentro da
        transação de ``issue``; aí o e-mail fica na fila em vez de se perder.
        """
        try:
            self.email_sender.send(
                "user_invite",
                {
                    "user_name": user.name,
                    "invite_link": self.invite_link(issued.token),
                    "expires_at": issued.expires_at.isoformat(),
                    "invited_by": invited_by,
                },
                to=user.email,
            )
        except EmailSendError:
            logger.exception("Invite email to user %s failed", user.id)
            return False
        return True

    # ---- ações do admin ---------------------------------------------------

    def latest_by_users(self, user_ids: list[int]) -> dict[int, UserInvite]:
        return self.invites.get_latest_by_users(user_ids)

    def _get_invited_user(self, user_id: int) -> User:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        if user.status != UserStatus.INVITED:
            raise UserNotInvitedError()
        return user

    def resend(self, user_id: int, admin: User) -> UserInvite:
        user = self._get_invited_user(user_id)
        limit = self.settings.invite_resend_limit_per_hour
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        if self.invites.count_created_since(user.id, since) >= limit:
            raise InviteResendLimitError(limit)

        with unit_of_work(self.invites.db):
            issued = self.issue(user, admin)
        self.send_invite_email(user, issued, admin.name)
        return self.invites.get_active_by_user(user.id)

    def cancel(self, user_id: int, admin: User) -> None:
        user = self._get_invited_user(user_id)
        active = self.invites.get_active_by_user(user.id)
        if active is None:
            raise InviteNotFoundError()
        with unit_of_work(self.invites.db):
            self.invites.update(active, {"revoked_at": datetime.now(timezone.utc)})
        logger.info("Invite of user %s cancelled by %s", user.id, admin.id)

    # ---- fluxo público ----------------------------------------------------

    def _validate(self, token: str, *, for_update: bool = False) -> UserInvite:
        invite = self.invites.get_by_token_hash(
            self.tokens.hash(token), for_update=for_update
        )
        # Inexistente e cancelado respondem igual: não revela se o token existe.
        if invite is None or invite.revoked_at is not None:
            raise InvalidInviteError()
        if invite.used_at is not None:
            raise InviteAlreadyUsedError()
        if self.tokens.is_expired(invite.expires_at):
            raise ExpiredInviteError()
        return invite

    def get_public(self, token: str) -> User:
        invite = self._validate(token)
        user = self.users.get_by_id(invite.user_id)
        if user is None or not user.is_active:
            raise InvalidInviteError()
        return user

    def accept(self, token: str, password: str) -> TokenResponse:
        with unit_of_work(self.invites.db):
            # FOR UPDATE: dois cliques simultâneos no link não consomem duas vezes.
            invite = self._validate(token, for_update=True)
            user = self.users.get_by_id(invite.user_id)
            # Usuário desativado pelo admin depois do convite não entra.
            if user is None or not user.is_active:
                raise InvalidInviteError()
            self.invites.update(invite, {"used_at": datetime.now(timezone.utc)})
            self.users.update(
                user,
                {
                    "hashed_password": hash_password(password),
                    "status": UserStatus.ACTIVE,
                    "updated_by": user.id,
                },
            )
        return TokenResponse(access_token=issue_access_token(user))
