from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.permissions.model import Permission, UserPermission


class PermissionRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[Permission]:
        return list(
            self.db.scalars(
                select(Permission).order_by(Permission.sort_order, Permission.id)
            ).all()
        )

    def get_keys_by_user(self, user_id: int) -> list[str]:
        return list(
            self.db.scalars(
                select(Permission.key)
                .join(UserPermission, UserPermission.permission_id == Permission.id)
                .where(UserPermission.user_id == user_id)
                .order_by(Permission.sort_order, Permission.id)
            ).all()
        )

    def replace_for_user(self, user_id: int, keys: Iterable[str]) -> None:
        """Substitui o conjunto inteiro de permissões do usuário."""
        self.db.execute(delete(UserPermission).where(UserPermission.user_id == user_id))
        wanted = set(keys)
        if wanted:
            permission_ids = self.db.scalars(
                select(Permission.id).where(Permission.key.in_(wanted))
            ).all()
            self.db.add_all(
                UserPermission(user_id=user_id, permission_id=permission_id)
                for permission_id in permission_ids
            )
        self.db.flush()
