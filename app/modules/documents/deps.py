from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.documents.drive_storage import DriveDocumentStorage
from app.modules.documents.repository import ProcessDocumentRepository
from app.modules.documents.service import ProcessDocumentService
from app.modules.documents.storage import DocumentStorage, LocalDocumentStorage
from app.modules.google_drive.deps import get_google_drive_service
from app.modules.google_drive.service import GoogleDriveService
from app.modules.processes.repository import ProcessRepository


def get_document_storages(
    drive: GoogleDriveService = Depends(get_google_drive_service),
) -> dict[str, DocumentStorage]:
    settings = get_settings()
    return {
        "local": LocalDocumentStorage(
            base_dir=settings.documents_upload_dir,
            max_size_mb=settings.document_max_file_size_mb,
            allowed_mime_types=settings.document_allowed_mime_types,
        ),
        "drive": DriveDocumentStorage(
            drive,
            max_size_mb=settings.document_max_file_size_mb,
            allowed_mime_types=settings.document_allowed_mime_types,
        ),
    }


def get_process_document_service(
    db: Session = Depends(get_db),
    storages: dict[str, DocumentStorage] = Depends(get_document_storages),
) -> ProcessDocumentService:
    return ProcessDocumentService(
        ProcessDocumentRepository(db),
        ProcessRepository(db),
        storages,
        get_settings().document_storage,
    )
