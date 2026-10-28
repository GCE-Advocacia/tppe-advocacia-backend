from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.audit_logs.repository import AuditLogRepository
from app.modules.audit_logs.service import AuditLogService
from app.modules.email.renderer import EmailRenderer
from app.modules.email_settings.connection_test import ConnectionTester
from app.modules.email_settings.repository import EmailProfileRepository
from app.modules.email_settings.service import EmailSettingsService
from app.shared.deps.email import get_email_renderer


def get_connection_tester() -> ConnectionTester:
    return ConnectionTester()


def get_email_settings_service(
    db: Session = Depends(get_db),
    tester: ConnectionTester = Depends(get_connection_tester),
    renderer: EmailRenderer = Depends(get_email_renderer),
) -> EmailSettingsService:
    return EmailSettingsService(
        repository=EmailProfileRepository(db),
        tester=tester,
        audit=AuditLogService(AuditLogRepository(db)),
        renderer=renderer,
        settings=get_settings(),
    )
