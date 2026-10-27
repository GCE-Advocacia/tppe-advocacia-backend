from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.modules.audit_logs.repository import AuditLogRepository
from app.modules.audit_logs.service import AuditLogService
from app.modules.email.protocol import EmailService
from app.modules.permissions.repository import PermissionRepository
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService
from app.shared.deps.email import get_email_service


def get_user_service(
    db: Session = Depends(get_db),
    email: EmailService = Depends(get_email_service),
) -> UserService:
    return UserService(
        UserRepository(db),
        email,
        AuditLogService(AuditLogRepository(db)),
        PermissionRepository(db),
    )
