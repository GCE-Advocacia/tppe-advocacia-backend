from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.users.invite_model import UserInvite


class InviteRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        created_by: int | None,
    ) -> UserInvite:
        invite = UserInvite(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_by=created_by,
        )
        self.db.add(invite)
        self.db.flush()
        return invite

    def get_active_by_user(self, user_id: int) -> UserInvite | None:
        return self.db.scalars(
            select(UserInvite)
            .where(
                UserInvite.user_id == user_id,
                UserInvite.used_at.is_(None),
                UserInvite.revoked_at.is_(None),
            )
            .order_by(UserInvite.created_at.desc(), UserInvite.id.desc())
        ).first()

    def get_latest_by_users(self, user_ids: list[int]) -> dict[int, UserInvite]:
        """Último convite (ativo ou não) de cada usuário, para a listagem."""
        if not user_ids:
            return {}
        invites = self.db.scalars(
            select(UserInvite)
            .where(UserInvite.user_id.in_(user_ids))
            .order_by(UserInvite.created_at.asc(), UserInvite.id.asc())
        ).all()
        # Em ordem crescente, o último de cada usuário sobrescreve os anteriores.
        return {invite.user_id: invite for invite in invites}

    def get_by_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> UserInvite | None:
        statement = select(UserInvite).where(UserInvite.token_hash == token_hash)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalars(statement).first()

    def count_created_since(self, user_id: int, since: datetime) -> int:
        return (
            self.db.scalar(
                select(func.count(UserInvite.id)).where(
                    UserInvite.user_id == user_id, UserInvite.created_at >= since
                )
            )
            or 0
        )

    def update(self, invite: UserInvite, data: dict) -> UserInvite:
        for key, value in data.items():
            setattr(invite, key, value)
        self.db.flush()
        return invite
