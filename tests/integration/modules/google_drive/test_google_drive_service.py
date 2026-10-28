from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.external_api_logs.model import (
    ExternalApiLog,
    ExternalApiOperation,
    ExternalApiProvider,
    ExternalApiStatus,
)
from app.modules.external_api_logs.repository import ExternalApiLogRepository
from app.modules.google_calendar.crypto import TokenCipher
from app.modules.google_calendar.service import GoogleOAuthError
from app.modules.google_drive import service as drive_service_module
from app.modules.google_drive.client import DriveApiError, DriveAuthRevokedError
from app.modules.google_drive.fake_client import FakeDriveClient
from app.modules.google_drive.repository import (
    GoogleDriveConnectionRepository,
    ProcessDriveFolderRepository,
)
from app.modules.google_drive.service import ROOT_FOLDER_NAME, GoogleDriveService
from app.modules.processes.repository import ProcessRepository
from app.modules.processes.schema import format_cnj
from app.modules.users.repository import UserRepository
from app.shared.exceptions import (
    GoogleDriveNotConfiguredError,
    GoogleDriveNotConnectedError,
    GoogleDriveUnavailableError,
)
from app.shared.types import Role

SECRET = "state-secret-with-enough-length-1234567890"
PROCESS_NUMBER = "00012345620248260100"


@pytest.fixture
def fake() -> FakeDriveClient:
    return FakeDriveClient()


@pytest.fixture
def users(db: Session) -> dict[str, int]:
    repo = UserRepository(db)
    admin = repo.create("Admin", "admin@example.test", "x", Role.ADMIN)
    user = repo.create("User", "user@example.test", "x", Role.USER)
    db.commit()
    return {"admin": admin.id, "user": user.id}


@pytest.fixture
def process_id(db: Session) -> int:
    client = ClientRepository(db).create(name="Cliente", cpf="11122233355")
    process = ProcessRepository(db).create(
        number=PROCESS_NUMBER, client_id=client.id, court="TJSP", action_type="Cível"
    )
    db.commit()
    return process.id


@pytest.fixture
def oauth() -> MagicMock:
    oauth = MagicMock()
    oauth.build_auth_url.side_effect = (
        lambda state: f"https://google.test/auth?state={state}"
    )
    oauth.exchange_code.return_value = ("refresh-token", "drive.file")
    return oauth


@pytest.fixture
def notifier() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(db, fake, oauth, notifier) -> GoogleDriveService:
    return GoogleDriveService(
        connections=GoogleDriveConnectionRepository(db),
        folders=ProcessDriveFolderRepository(db),
        users=UserRepository(db),
        log_repository=ExternalApiLogRepository(db),
        notifier=notifier,
        oauth=oauth,
        cipher=TokenCipher(Fernet.generate_key().decode()),
        state_secret=SECRET,
        client_factory=lambda refresh_token: fake,
    )


def state_from(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


def connect(service: GoogleDriveService, admin_id: int) -> None:
    service.handle_callback("code", state_from(service.build_auth_url(admin_id)))


def failure_logs(db: Session) -> list[ExternalApiLog]:
    return db.query(ExternalApiLog).all()


class TestConnection:
    def test_status_disconnected_then_connected_with_email(self, service, users):
        assert service.get_status().connected is False
        connect(service, users["admin"])
        status = service.get_status()
        assert status.connected is True
        assert status.email == "escritorio@example.test"

    def test_auth_url_requires_configuration(self, service, users):
        service.oauth = None
        with pytest.raises(GoogleDriveNotConfiguredError):
            service.build_auth_url(users["admin"])

    def test_callback_rejects_calendar_state(self, service, users, db):
        calendar_state = jwt.encode(
            {
                "sub": str(users["admin"]),
                "purpose": "google_oauth",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            SECRET,
            algorithm="HS256",
        )
        with pytest.raises(GoogleOAuthError):
            service.handle_callback("code", calendar_state)
        assert service.get_status().connected is False
        assert failure_logs(db) == []

    def test_callback_rejects_non_admin(self, service, users):
        state = state_from(service.build_auth_url(users["user"]))
        with pytest.raises(GoogleOAuthError):
            service.handle_callback("code", state)
        assert service.get_status().connected is False

    def test_callback_saves_encrypted_token_and_email(self, service, users, db):
        connect(service, users["admin"])
        connection = GoogleDriveConnectionRepository(db).get()
        assert connection.encrypted_refresh_token != "refresh-token"
        assert service.cipher.decrypt(connection.encrypted_refresh_token) == (
            "refresh-token"
        )
        assert connection.connected_by == users["admin"]

    def test_failed_code_exchange_is_logged_as_oauth_failure(
        self, service, users, oauth, notifier, db
    ):
        oauth.exchange_code.side_effect = RuntimeError("google down")
        with pytest.raises(GoogleOAuthError):
            connect(service, users["admin"])
        [log] = failure_logs(db)
        assert log.provider == ExternalApiProvider.GOOGLE_DRIVE
        assert log.operation == ExternalApiOperation.OAUTH
        notifier.notify_failure.assert_called_once()

    def test_disconnect_revokes_and_deletes(self, service, users, monkeypatch):
        revoked = []
        monkeypatch.setattr(
            drive_service_module, "revoke_refresh_token", revoked.append
        )
        connect(service, users["admin"])
        service.disconnect()
        assert revoked == ["refresh-token"]
        assert service.get_status().connected is False

    def test_client_without_connection_raises_not_connected(self, service):
        with pytest.raises(GoogleDriveNotConnectedError):
            service.client()


class TestFolders:
    def test_root_and_process_folders_are_created_once_then_reused(
        self, service, users, process_id, fake
    ):
        connect(service, users["admin"])
        client = service.client()
        first = service.process_folder_id(client, process_id, PROCESS_NUMBER)
        second = service.process_folder_id(client, process_id, PROCESS_NUMBER)

        assert first == second
        assert len(fake.folders) == 2
        name, parent = fake.folders[first]
        assert name == format_cnj(PROCESS_NUMBER)
        assert fake.folders[parent] == (ROOT_FOLDER_NAME, None)

    @pytest.mark.parametrize("which", ["root", "process"])
    def test_missing_or_trashed_folder_is_recreated_and_saved(
        self, service, users, process_id, fake, db, which
    ):
        connect(service, users["admin"])
        client = service.client()
        process_folder = service.process_folder_id(client, process_id, PROCESS_NUMBER)
        root_folder = fake.folders[process_folder][1]
        fake.trash_file(root_folder if which == "root" else process_folder)

        new_folder = service.process_folder_id(client, process_id, PROCESS_NUMBER)

        assert new_folder != process_folder
        assert fake.folder_exists(new_folder)
        assert fake.folder_exists(fake.folders[new_folder][1])
        assert ProcessDriveFolderRepository(db).get_folder_id(process_id) == new_folder


class TestFailures:
    def test_fail_with_revoked_token_disconnects_and_raises_not_connected(
        self, service, users, notifier, db
    ):
        connect(service, users["admin"])
        with pytest.raises(GoogleDriveNotConnectedError):
            service.fail(
                ExternalApiOperation.DOCUMENT_UPLOAD,
                DriveAuthRevokedError("invalid_grant"),
                user_id=users["admin"],
            )
        assert service.get_status().connected is False
        [log] = failure_logs(db)
        assert log.provider == ExternalApiProvider.GOOGLE_DRIVE
        assert log.operation == ExternalApiOperation.DOCUMENT_UPLOAD
        assert log.status == ExternalApiStatus.FAILURE
        notifier.notify_failure.assert_called_once_with(log)

    def test_fail_with_api_error_raises_unavailable_and_keeps_connection(
        self, service, users, db
    ):
        connect(service, users["admin"])
        with pytest.raises(GoogleDriveUnavailableError):
            service.fail(
                ExternalApiOperation.DOCUMENT_DOWNLOAD,
                DriveApiError(500, "boom"),
                user_id=users["user"],
                process_id=None,
            )
        assert service.get_status().connected is True
        [log] = failure_logs(db)
        assert log.http_status == 500
        assert log.created_by == users["user"]
