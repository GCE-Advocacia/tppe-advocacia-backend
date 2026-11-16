from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit_logs.model import AuditAction, AuditLog


class AuditLogRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        action: AuditAction,
        performed_by_id: int | None,
        performed_by_name: str | None,
        target_user_id: int | None = None,
        target_user_name: str | None = None,
        target_user_email: str | None = None,
        target_user_role: str | None = None,
        target_client_id: int | None = None,
        target_client_name: str | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        log = AuditLog(
            action=action,
            performed_by_id=performed_by_id,
            performed_by_name=performed_by_name,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            target_user_email=target_user_email,
            target_user_role=target_user_role,
            target_client_id=target_client_id,
            target_client_name=target_client_name,
            details=details,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def get_all(
        self,
        action: AuditAction | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[AuditLog], int]:
        statement = select(AuditLog).order_by(AuditLog.created_at.desc())
        count_statement = select(func.count()).select_from(AuditLog)

        if action is not None:
            statement = statement.where(AuditLog.action == action)
            count_statement = count_statement.where(AuditLog.action == action)

        if date_from is not None:
            statement = statement.where(AuditLog.created_at >= date_from)
            count_statement = count_statement.where(AuditLog.created_at >= date_from)

        if date_to is not None:
            statement = statement.where(AuditLog.created_at <= date_to)
            count_statement = count_statement.where(AuditLog.created_at <= date_to)

        total = self.db.scalar(count_statement) or 0
        logs = list(
            self.db.scalars(statement.offset((page - 1) * limit).limit(limit)).all()
        )
        return logs, total
