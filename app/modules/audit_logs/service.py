from datetime import datetime

from app.modules.audit_logs.model import AuditAction, AuditLog
from app.modules.audit_logs.repository import AuditLogRepository
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work


class AuditLogService:
    def __init__(self, repository: AuditLogRepository) -> None:
        self.repository = repository

    def log_user_created(self, user: User, performed_by: User) -> None:
        with unit_of_work(self.repository.db):
            self.repository.create(
                action=AuditAction.USER_CREATED,
                performed_by_id=performed_by.id,
                performed_by_name=performed_by.name,
                target_user_id=user.id,
                target_user_name=user.name,
                target_user_email=user.email,
                target_user_role=user.role.value,
            )

    def log_user_updated(self, user: User, performed_by: User) -> None:
        with unit_of_work(self.repository.db):
            self.repository.create(
                action=AuditAction.USER_UPDATED,
                performed_by_id=performed_by.id,
                performed_by_name=performed_by.name,
                target_user_id=user.id,
                target_user_name=user.name,
                target_user_email=user.email,
                target_user_role=user.role.value,
            )

    def log_user_deactivated(self, user: User, performed_by: User) -> None:
        with unit_of_work(self.repository.db):
            self.repository.create(
                action=AuditAction.USER_DEACTIVATED,
                performed_by_id=performed_by.id,
                performed_by_name=performed_by.name,
                target_user_id=user.id,
                target_user_name=user.name,
                target_user_email=user.email,
                target_user_role=user.role.value,
            )

    def log_client_anonymized(
        self,
        client_id: int,
        client_name: str,
        performed_by: User,
    ) -> None:
        self.repository.create(
            action=AuditAction.CLIENT_ANONYMIZED,
            performed_by_id=performed_by.id,
            performed_by_name=performed_by.name,
            target_client_id=client_id,
            target_client_name=client_name,
        )

    def log_email_settings_updated(
        self, profile_name: str, changes: dict, performed_by: User
    ) -> None:
        """Sem commit próprio: grava na transação de quem salvou o perfil.
        ``changes`` já vem sem segredo (``"secret": "alterado"``)."""
        self.repository.create(
            action=AuditAction.EMAIL_SETTINGS_UPDATED,
            performed_by_id=performed_by.id,
            performed_by_name=performed_by.name,
            details={"profile": profile_name, "changes": changes},
        )

    def list_logs(
        self,
        action: AuditAction | None,
        date_from: datetime | None,
        date_to: datetime | None,
        page: int,
        limit: int,
    ) -> tuple[list[AuditLog], int]:
        return self.repository.get_all(
            action=action, date_from=date_from, date_to=date_to, page=page, limit=limit
        )
