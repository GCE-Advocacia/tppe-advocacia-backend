from __future__ import annotations

import logging
from io import BytesIO
from typing import Protocol

import httpx
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from app.config.settings import Settings

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"  # public OAuth URL  # nosec B105
_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
_FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveAuthRevokedError(Exception):
    """O refresh_token foi revogado ou expirou (invalid_grant)."""


class DriveNotFoundError(Exception):
    """O arquivo ou pasta não existe (ou o sistema não tem acesso a ele)."""


class DriveApiError(Exception):
    def __init__(self, http_status: int | None, message: str) -> None:
        super().__init__(message)
        self.http_status = http_status


class DriveClient(Protocol):
    def create_folder(self, name: str, parent_id: str | None) -> str: ...

    def folder_exists(self, folder_id: str) -> bool: ...

    def upload_file(
        self, name: str, content: bytes, mime_type: str, parent_id: str
    ) -> str: ...

    def download_file(self, file_id: str) -> bytes: ...

    def trash_file(self, file_id: str) -> None: ...

    def get_email(self) -> str | None: ...


class GoogleDriveApiClient:
    """Implementação real de `DriveClient` via Google Drive API v3.

    Toda chamada passa por `_execute`, que converte as exceções do Google nos
    três erros deste módulo.
    """

    def __init__(self, refresh_token: str, settings: Settings, service=None) -> None:
        if service is None:
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri=_TOKEN_URI,
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=DRIVE_SCOPES,
            )
            service = build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            )
        self._service = service

    @staticmethod
    def _execute(call):
        try:
            return call()
        except HttpError as exc:
            if exc.resp.status == 404:
                raise DriveNotFoundError(str(exc)) from exc
            raise DriveApiError(exc.resp.status, str(exc)) from exc
        except RefreshError as exc:
            if "invalid_grant" in str(exc):
                raise DriveAuthRevokedError(str(exc)) from exc
            raise DriveApiError(None, str(exc)) from exc
        except (DriveAuthRevokedError, DriveNotFoundError, DriveApiError):
            raise
        except Exception as exc:
            # Timeout, falha de rede ou resposta inesperada.
            raise DriveApiError(None, str(exc) or type(exc).__name__) from exc

    def create_folder(self, name: str, parent_id: str | None) -> str:
        body = {"name": name, "mimeType": _FOLDER_MIME}
        if parent_id:
            body["parents"] = [parent_id]
        created = self._execute(
            lambda: self._service.files().create(body=body, fields="id").execute()
        )
        return created["id"]

    def folder_exists(self, folder_id: str) -> bool:
        try:
            metadata = self._execute(
                lambda: self._service.files()
                .get(fileId=folder_id, fields="id,trashed")
                .execute()
            )
        except DriveNotFoundError:
            return False
        return not metadata.get("trashed", False)

    def upload_file(
        self, name: str, content: bytes, mime_type: str, parent_id: str
    ) -> str:
        media = MediaIoBaseUpload(BytesIO(content), mimetype=mime_type, resumable=False)
        created = self._execute(
            lambda: self._service.files()
            .create(
                body={"name": name, "parents": [parent_id]},
                media_body=media,
                fields="id",
            )
            .execute()
        )
        return created["id"]

    def download_file(self, file_id: str) -> bytes:
        def download() -> bytes:
            buffer = BytesIO()
            downloader = MediaIoBaseDownload(
                buffer, self._service.files().get_media(fileId=file_id)
            )
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue()

        return self._execute(download)

    def trash_file(self, file_id: str) -> None:
        self._execute(
            lambda: self._service.files()
            .update(fileId=file_id, body={"trashed": True})
            .execute()
        )

    def get_email(self) -> str | None:
        about = self._execute(
            lambda: self._service.about().get(fields="user(emailAddress)").execute()
        )
        return about.get("user", {}).get("emailAddress")


def revoke_refresh_token(refresh_token: str) -> None:
    """Revoga o token no Google. Falhas são ignoradas: a desconexão local vale."""
    try:
        httpx.post(_REVOKE_URI, data={"token": refresh_token}, timeout=10)
    except Exception:
        logger.warning("Could not revoke Google Drive token", exc_info=True)
