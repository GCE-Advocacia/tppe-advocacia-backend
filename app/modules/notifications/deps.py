from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.modules.email.sender import TemplateSender
from app.modules.notifications.repository import NotificationPreferenceRepository
from app.modules.notifications.service import NotificationService
from app.modules.users.repository import UserRepository
from app.shared.deps.email import get_queued_sender


def get_notification_service(
    db: Session = Depends(get_db),
    email_sender: TemplateSender = Depends(get_queued_sender),
) -> NotificationService:
    return NotificationService(
        NotificationPreferenceRepository(db),
        UserRepository(db),
        email_sender,
    )
