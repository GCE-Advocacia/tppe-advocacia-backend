from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.audit_logs.repository import AuditLogRepository
from app.modules.audit_logs.service import AuditLogService
from app.modules.email.sender import TemplatedEmailSender
from app.modules.users.invite_repository import InviteRepository
from app.modules.users.invite_service import InviteService
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService
from app.shared.deps.email import get_templated_sender


def get_invite_service(
    db: Session = Depends(get_db),
    email_sender: TemplatedEmailSender = Depends(get_templated_sender),
) -> InviteService:
    return InviteService(
        InviteRepository(db), UserRepository(db), email_sender, get_settings()
    )


def get_user_service(
    db: Session = Depends(get_db),
    invites: InviteService = Depends(get_invite_service),
) -> UserService:
    return UserService(
        UserRepository(db),
        invites,
        AuditLogService(AuditLogRepository(db)),
    )
