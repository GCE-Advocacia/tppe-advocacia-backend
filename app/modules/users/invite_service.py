import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config.settings import Settings
from app.modules.auth.schema import TokenResponse
from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus
from app.modules.email_outbox.service import EmailOutbox
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

INVITE_TEMPLATE = "user_invite"
INVITE_RELATED_TYPE = "user"


@dataclass(frozen=True)
class IssuedInvite:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class InviteEmail:
    """Situação do e-mail do convite mais recente, vinda da fila."""

    status: EmailStatus
    last_sent_at: datetime | None


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
        outbox: EmailOutbox,
        settings: Settings,
        tokens: OneTimeTokenService | None = None,
    ) -> None:
        self.invites = invites
        self.users = users
        self.outbox = outbox
        self.settings = settings
        self.tokens = tokens or OneTimeTokenService()

    # ---- emissão (dentro da transação de quem chama) ---------------------

    def issue(self, user: User, created_by: User | None) -> IssuedInvite:
        """Revoga o convite ativo (se houver), cria outro e põe o e-mail na
        fila. Não comita: quem chama envolve em ``unit_of_work``, então
        usuário, convite e e-mail entram ou saem juntos. O token em texto só
        existe no retorno e no contexto do item da fila até o envio."""
        now = datetime.now(timezone.utc)
        active = self.invites.get_active_by_user(user.id)
        if active is not None:
            self.invites.update(active, {"revoked_at": now})
            self.outbox.cancel_pending(f"invite:{active.id}")
        token, token_hash = self.tokens.generate()
        expires_at = self.tokens.expires_at(
            timedelta(hours=self.settings.invite_expire_hours), now
        )
        invite = self.invites.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_by=created_by.id if created_by else None,
        )
        self.outbox.enqueue(
            INVITE_TEMPLATE,
            {
                "user_name": user.name,
                "invite_link": self.invite_link(token),
                "expires_at": expires_at.isoformat(),
                "invited_by": created_by.name if created_by else None,
            },
            to=user.email,
            related=(INVITE_RELATED_TYPE, user.id),
            idempotency_key=f"invite:{invite.id}",
            created_by=created_by.id if created_by else None,
        )
        return IssuedInvite(token=token, expires_at=expires_at)

    def invite_link(self, token: str) -> str:
        return f"{self.settings.frontend_url}/convite/{token}"

    # ---- ações do admin ---------------------------------------------------

    def latest_by_users(self, user_ids: list[int]) -> dict[int, UserInvite]:
        return self.invites.get_latest_by_users(user_ids)

    def emails_by_users(self, user_ids: list[int]) -> dict[int, InviteEmail]:
        """Status do último e-mail de convite e data do último envio que
        saiu de fato, por usuário."""
        items = self.outbox.repository.list_related(
            INVITE_RELATED_TYPE, user_ids, INVITE_TEMPLATE
        )
        latest: dict[int, EmailOutboxItem] = {}
        last_sent: dict[int, datetime] = {}
        # Em ordem crescente, o último de cada usuário sobrescreve os anteriores.
        for item in items:
            latest[item.related_id] = item
            if item.status == EmailStatus.SENT and item.sent_at is not None:
                last_sent[item.related_id] = item.sent_at
        return {
            user_id: InviteEmail(
                status=item.status, last_sent_at=last_sent.get(user_id)
            )
            for user_id, item in latest.items()
        }

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
            self.issue(user, admin)
        return self.invites.get_active_by_user(user.id)

    def cancel(self, user_id: int, admin: User) -> None:
        user = self._get_invited_user(user_id)
        active = self.invites.get_active_by_user(user.id)
        if active is None:
            raise InviteNotFoundError()
        with unit_of_work(self.invites.db):
            self.invites.update(active, {"revoked_at": datetime.now(timezone.utc)})
            self.outbox.cancel_pending(f"invite:{active.id}")
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
