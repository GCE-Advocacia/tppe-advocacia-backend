from fastapi import Depends
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.documents.repository import ProcessDocumentRepository
from app.modules.documents.service import ProcessDocumentService
from app.modules.documents.storage import DocumentStorage, LocalDocumentStorage
from app.modules.processes.repository import ProcessRepository


def get_document_storage() -> DocumentStorage:
    settings = get_settings()
    return LocalDocumentStorage(
        base_dir=settings.documents_upload_dir,
        max_size_mb=settings.document_max_file_size_mb,
        allowed_mime_types=settings.document_allowed_mime_types,
    )


def get_process_document_service(
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_document_storage),
) -> ProcessDocumentService:
    return ProcessDocumentService(
        ProcessDocumentRepository(db),
        ProcessRepository(db),
        storage,
    )
