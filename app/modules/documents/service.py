from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from app.modules.documents.model import ProcessDocument
from app.modules.documents.repository import ProcessDocumentRepository
from app.modules.documents.storage import DocumentStorage
from app.modules.processes.repository import ProcessRepository
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import ProcessDocumentNotFoundError, ProcessNotFoundError
from app.shared.service.helpers import assert_author_or_admin, get_or_raise

_FALLBACK_NAME = "documento"
_MAX_NAME_LENGTH = 255


def sanitize_original_name(raw: str | None) -> str:
    """Mantém só o basename imprimível do nome enviado pelo navegador."""
    name = PurePosixPath((raw or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    if name in {".", ".."}:
        return _FALLBACK_NAME
    return name[:_MAX_NAME_LENGTH] or _FALLBACK_NAME


class ProcessDocumentService:
    def __init__(
        self,
        repository: ProcessDocumentRepository,
        process_repository: ProcessRepository,
        storage: DocumentStorage,
    ) -> None:
        self.repository = repository
        self.process_repository = process_repository
        self.storage = storage

    def upload(
        self, process_id: int, file: UploadFile, current_user: User
    ) -> ProcessDocument:
        self._ensure_process(process_id)
        stored = self.storage.save(file)
        try:
            with unit_of_work(self.repository.db):
                document = self.repository.create(
                    process_id=process_id,
                    original_name=sanitize_original_name(file.filename),
                    stored_name=stored.stored_name,
                    mime_type=stored.mime_type,
                    size_bytes=stored.size_bytes,
                    uploaded_by=current_user.id,
                )
        except Exception:
            self.storage.delete(stored.stored_name)
            raise
        return document

    def list_documents(
        self, process_id: int, page: int = 1, limit: int = 20
    ) -> tuple[list[ProcessDocument], int]:
        self._ensure_process(process_id)
        return self.repository.list_by_process(
            process_id=process_id, page=page, limit=limit
        )

    def get_download(
        self, process_id: int, document_id: int
    ) -> tuple[ProcessDocument, Path]:
        document = self._get_document(process_id, document_id)
        return document, self.storage.path_for(document.stored_name)

    def delete(self, process_id: int, document_id: int, current_user: User) -> None:
        document = self._get_document(process_id, document_id)
        assert_author_or_admin(current_user, document.uploaded_by)

        stored_name = document.stored_name
        with unit_of_work(self.repository.db):
            self.repository.delete(document)
        self.storage.delete(stored_name)

    def _ensure_process(self, process_id: int) -> None:
        get_or_raise(
            lambda: self.process_repository.get_by_id(process_id),
            ProcessNotFoundError,
        )

    def _get_document(self, process_id: int, document_id: int) -> ProcessDocument:
        self._ensure_process(process_id)
        return get_or_raise(
            lambda: self.repository.get_by_id(
                document_id=document_id, process_id=process_id
            ),
            ProcessDocumentNotFoundError,
        )
