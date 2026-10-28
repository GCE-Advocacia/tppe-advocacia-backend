from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import NoReturn

import jwt
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.modules.external_api_logs.model import (
    ExternalApiOperation,
    ExternalApiProvider,
    ExternalApiStatus,
)
from app.modules.external_api_logs.notifier import ExternalApiFailureNotifier
from app.modules.external_api_logs.repository import ExternalApiLogRepository
from app.modules.google_calendar.crypto import TokenCipher
from app.modules.google_calendar.oauth import GoogleOAuthFlow
from app.modules.google_calendar.service import GoogleOAuthError
from app.modules.google_drive.client import (
    DRIVE_SCOPES,
    DriveApiError,
    DriveAuthRevokedError,
    DriveClient,
    GoogleDriveApiClient,
    revoke_refresh_token,
)
from app.modules.google_drive.repository import (
    GoogleDriveConnectionRepository,
    ProcessDriveFolderRepository,
)
from app.modules.google_drive.schema import GoogleDriveStatusRead
from app.modules.notifications.service import NotificationService
from app.modules.processes.schema import format_cnj
from app.modules.users.repository import UserRepository
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import (
    GoogleDriveNotConfiguredError,
    GoogleDriveNotConnectedError,
    GoogleDriveUnavailableError,
)
from app.shared.types import Role

logger = logging.getLogger(__name__)

ROOT_FOLDER_NAME = "Sistema Advocacia — Documentos"
_STATE_PURPOSE = "google_drive"
_STATE_TTL_MINUTES = 10


class GoogleDriveService:
    """Conexão única do escritório com o Google Drive e as pastas do sistema."""

    def __init__(
        self,
        connections: GoogleDriveConnectionRepository,
        folders: ProcessDriveFolderRepository,
        users: UserRepository,
        log_repository: ExternalApiLogRepository,
        notifier: ExternalApiFailureNotifier | None,
        oauth: GoogleOAuthFlow | None,
        cipher: TokenCipher | None,
        state_secret: str,
        client_factory: Callable[[str], DriveClient],
    ) -> None:
        self.connections = connections
        self.folders = folders
        self.users = users
        self.log_repository = log_repository
        self.notifier = notifier
        self.oauth = oauth
        self.cipher = cipher
        self.state_secret = state_secret
        self.client_factory = client_factory

    @property
    def db(self) -> Session:
        return self.connections.db

    # ----- conexão --------------------------------------------------------

    def get_status(self) -> GoogleDriveStatusRead:
        connection = self.connections.get()
        if connection is None:
            return GoogleDriveStatusRead(connected=False)
        return GoogleDriveStatusRead(connected=True, email=connection.email)

    def build_auth_url(self, user_id: int) -> str:
        if self.oauth is None or self.cipher is None:
            raise GoogleDriveNotConfiguredError()
        return self.oauth.build_auth_url(self._encode_state(user_id))

    def handle_callback(self, code: str, state: str) -> None:
        """Levanta GoogleOAuthError em qualquer falha; o router redireciona."""
        if self.oauth is None or self.cipher is None:
            raise GoogleOAuthError("Google Drive integration is not configured")

        user_id = self._decode_state(state)
        user = self.users.get_by_id(user_id)
        if user is None or user.role != Role.ADMIN or not user.is_active:
            raise GoogleOAuthError("Only active administrators can connect Drive")

        try:
            refresh_token, _ = self.oauth.exchange_code(code)
        except Exception as exc:  # noqa: BLE001
            self._record_failure(ExternalApiOperation.OAUTH, exc, user_id)
            raise GoogleOAuthError("Failed to exchange authorization code") from exc
        if not refresh_token:
            raise GoogleOAuthError("Google did not return a refresh token")

        try:
            email = self.client_factory(refresh_token).get_email()
        except Exception:  # noqa: BLE001
            # O e-mail é só informativo: não impede a conexão.
            logger.warning("Could not read Google Drive account email", exc_info=True)
            email = None

        with unit_of_work(self.db):
            self.connections.save(self.cipher.encrypt(refresh_token), email, user_id)

    def disconnect(self) -> None:
        connection = self.connections.get()
        if connection is None:
            return
        if self.cipher is not None:
            revoke_refresh_token(
                self.cipher.decrypt(connection.encrypted_refresh_token)
            )
        with unit_of_work(self.db):
            self.connections.delete()

    def client(self) -> DriveClient:
        connection = self.connections.get()
        if connection is None or self.cipher is None:
            raise GoogleDriveNotConnectedError()
        return self.client_factory(
            self.cipher.decrypt(connection.encrypted_refresh_token)
        )

    # ----- pastas ---------------------------------------------------------

    def root_folder_id(self, client: DriveClient) -> str:
        connection = self.connections.get()
        if connection is None:
            raise GoogleDriveNotConnectedError()
        if connection.root_folder_id and client.folder_exists(
            connection.root_folder_id
        ):
            return connection.root_folder_id
        folder_id = client.create_folder(ROOT_FOLDER_NAME, None)
        with unit_of_work(self.db):
            self.connections.set_root_folder(folder_id)
        return folder_id

    def process_folder_id(
        self, client: DriveClient, process_id: int, process_number: str
    ) -> str:
        folder_id = self.folders.get_folder_id(process_id)
        if folder_id and client.folder_exists(folder_id):
            return folder_id
        root_id = self.root_folder_id(client)
        folder_id = client.create_folder(format_cnj(process_number), root_id)
        with unit_of_work(self.db):
            self.folders.set_folder_id(process_id, folder_id)
        return folder_id

    # ----- falhas ---------------------------------------------------------

    def fail(
        self,
        operation: ExternalApiOperation,
        exc: Exception,
        user_id: int | None,
        process_id: int | None = None,
    ) -> NoReturn:
        """Registra a falha, avisa os admins e levanta o erro para a API."""
        self._record_failure(operation, exc, user_id, process_id)
        if isinstance(exc, DriveAuthRevokedError):
            with unit_of_work(self.db):
                self.connections.delete()
            raise GoogleDriveNotConnectedError() from exc
        raise GoogleDriveUnavailableError() from exc

    def _record_failure(
        self,
        operation: ExternalApiOperation,
        exc: Exception,
        user_id: int | None,
        process_id: int | None = None,
    ) -> None:
        logger.warning("Google Drive %s failed: %s", operation.value, exc)
        http_status = exc.http_status if isinstance(exc, DriveApiError) else None
        # Transação própria: a falha fica registrada mesmo que a operação aborte.
        with unit_of_work(self.db):
            log = self.log_repository.create(
                provider=ExternalApiProvider.GOOGLE_DRIVE,
                operation=operation,
                status=ExternalApiStatus.FAILURE,
                process_id=process_id,
                http_status=http_status,
                error_code=type(exc).__name__[:50],
                error_message=str(exc)[:500] or type(exc).__name__,
                created_by=user_id,
            )
        if self.notifier is not None:
            self.notifier.notify_failure(log)

    # ----- state assinado (CSRF + identifica o admin no callback) ----------

    def _encode_state(self, user_id: int) -> str:
        payload = {
            "sub": str(user_id),
            "purpose": _STATE_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_TTL_MINUTES),
        }
        return jwt.encode(payload, self.state_secret, algorithm="HS256")

    def _decode_state(self, state: str) -> int:
        try:
            data = jwt.decode(state, self.state_secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise GoogleOAuthError("Invalid or expired OAuth state") from exc
        if data.get("purpose") != _STATE_PURPOSE:
            raise GoogleOAuthError("Invalid OAuth state")
        return int(data["sub"])


def build_google_drive_service(
    db: Session,
    client_factory: Callable[[str], DriveClient] | None = None,
    notifications: NotificationService | None = None,
) -> GoogleDriveService:
    settings = get_settings()
    configured = settings.google_drive_configured
    return GoogleDriveService(
        connections=GoogleDriveConnectionRepository(db),
        folders=ProcessDriveFolderRepository(db),
        users=UserRepository(db),
        log_repository=ExternalApiLogRepository(db),
        notifier=(
            ExternalApiFailureNotifier(
                UserRepository(db), notifications, ExternalApiLogRepository(db)
            )
            if notifications is not None
            else None
        ),
        oauth=(
            GoogleOAuthFlow(
                settings,
                scopes=DRIVE_SCOPES,
                redirect_uri=settings.google_drive_redirect_uri,
                include_granted_scopes=False,
            )
            if configured
            else None
        ),
        cipher=(
            TokenCipher(settings.google_token_encryption_key) if configured else None
        ),
        state_secret=settings.jwt_secret_key,
        client_factory=client_factory
        or (lambda refresh_token: GoogleDriveApiClient(refresh_token, settings)),
    )
