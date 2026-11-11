from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.google_drive.client import DriveClient, GoogleDriveApiClient
from app.modules.google_drive.service import (
    GoogleDriveService,
    build_google_drive_service,
)
from app.modules.notifications.deps import get_notification_service
from app.modules.notifications.service import NotificationService


def get_drive_client_factory() -> Callable[[str], DriveClient]:
    settings = get_settings()
    return lambda refresh_token: GoogleDriveApiClient(refresh_token, settings)


def get_google_drive_service(
    db: Session = Depends(get_db),
    client_factory: Callable[[str], DriveClient] = Depends(get_drive_client_factory),
    notifications: NotificationService = Depends(get_notification_service),
) -> GoogleDriveService:
    return build_google_drive_service(db, client_factory, notifications)
