from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.audit_logs.repository import AuditLogRepository
from app.modules.audit_logs.service import AuditLogService
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.service import EmailOutbox
from app.modules.users.invite_repository import InviteRepository
from app.modules.users.invite_service import InviteService
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService


def get_invite_service(db: Session = Depends(get_db)) -> InviteService:
    return InviteService(
        InviteRepository(db),
        UserRepository(db),
        EmailOutbox(EmailOutboxRepository(db)),
        get_settings(),
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
