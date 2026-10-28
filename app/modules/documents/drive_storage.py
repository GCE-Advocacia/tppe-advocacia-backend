from fastapi import UploadFile

from app.modules.documents.storage import StoredFile, read_validated
from app.modules.external_api_logs.model import ExternalApiOperation
from app.modules.google_drive.client import (
    DriveApiError,
    DriveAuthRevokedError,
    DriveNotFoundError,
)
from app.modules.google_drive.service import GoogleDriveService
from app.shared.exceptions import ProcessDocumentNotFoundError

_DRIVE_ERRORS = (DriveAuthRevokedError, DriveNotFoundError, DriveApiError)


class DriveDocumentStorage:
    """Documentos no Google Drive do escritório, uma pasta por processo.

    `stored_name` guarda o ID do arquivo no Drive. Toda falha de comunicação
    passa por `GoogleDriveService.fail`, que registra e avisa os admins.
    """

    name = "drive"

    def __init__(
        self,
        drive: GoogleDriveService,
        max_size_mb: int,
        allowed_mime_types: list[str],
    ) -> None:
        self.drive = drive
        self.max_size_mb = max_size_mb
        self.allowed_mime_types = allowed_mime_types

    def save(
        self,
        file: UploadFile,
        *,
        process_id: int | None = None,
        process_number: str | None = None,
        original_name: str | None = None,
        user_id: int | None = None,
    ) -> StoredFile:
        content, mime, extension = read_validated(
            file, self.max_size_mb, self.allowed_mime_types
        )
        client = self.drive.client()
        try:
            folder_id = self.drive.process_folder_id(client, process_id, process_number)
            file_id = client.upload_file(
                original_name or f"documento.{extension}", content, mime, folder_id
            )
        except _DRIVE_ERRORS as exc:
            self.drive.fail(
                ExternalApiOperation.DOCUMENT_UPLOAD, exc, user_id, process_id
            )
        return StoredFile(
            stored_name=file_id,
            mime_type=mime,
            size_bytes=len(content),
            storage=self.name,
        )

    def read(self, stored_name: str) -> bytes:
        client = self.drive.client()
        try:
            return client.download_file(stored_name)
        except DriveNotFoundError as exc:
            # O arquivo foi apagado direto no Drive.
            raise ProcessDocumentNotFoundError() from exc
        except _DRIVE_ERRORS as exc:
            self.drive.fail(ExternalApiOperation.DOCUMENT_DOWNLOAD, exc, None)

    def ensure_available(self) -> None:
        # Levanta GoogleDriveNotConnectedError antes de qualquer mudança no banco.
        self.drive.client()

    def delete(self, stored_name: str, user_id: int | None = None) -> None:
        client = self.drive.client()
        try:
            client.trash_file(stored_name)
        except DriveNotFoundError:
            return  # já não existe no Drive
        except _DRIVE_ERRORS as exc:
            self.drive.fail(ExternalApiOperation.DOCUMENT_DELETE, exc, user_id)
