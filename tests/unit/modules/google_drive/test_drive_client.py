from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from app.config.settings import get_settings
from app.modules.google_drive.client import (
    DriveApiError,
    DriveAuthRevokedError,
    DriveNotFoundError,
    GoogleDriveApiClient,
)
from app.modules.google_drive.fake_client import FakeDriveClient


def client_with_responses(*responses):
    service = build(
        "drive",
        "v3",
        http=HttpMockSequence(list(responses)),
        static_discovery=True,
    )
    return GoogleDriveApiClient("refresh", get_settings(), service=service)


def client_with_service(service):
    return GoogleDriveApiClient("refresh", get_settings(), service=service)


class TestGoogleDriveApiClient:
    def test_http_404_becomes_not_found(self):
        client = client_with_responses(({"status": "404"}, b"{}"))
        with pytest.raises(DriveNotFoundError):
            client.download_file("missing")

    def test_http_500_becomes_api_error_with_status(self):
        client = client_with_responses(({"status": "500"}, b"{}"))
        with pytest.raises(DriveApiError) as exc:
            client.trash_file("file")
        assert exc.value.http_status == 500

    def test_refresh_error_becomes_auth_revoked(self):
        service = MagicMock()
        service.files.return_value.update.return_value.execute.side_effect = (
            RefreshError("invalid_grant: Token has been expired or revoked.")
        )
        with pytest.raises(DriveAuthRevokedError):
            client_with_service(service).trash_file("file")

    def test_other_refresh_error_becomes_api_error(self):
        service = MagicMock()
        service.files.return_value.update.return_value.execute.side_effect = (
            RefreshError("temporary network failure")
        )
        with pytest.raises(DriveApiError):
            client_with_service(service).trash_file("file")

    def test_timeout_becomes_api_error_without_status(self):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.side_effect = TimeoutError()
        with pytest.raises(DriveApiError) as exc:
            client_with_service(service).folder_exists("folder")
        assert exc.value.http_status is None

    def test_upload_sends_parent_and_no_permissions(self):
        service = MagicMock()
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "new-file"
        }
        file_id = client_with_service(service).upload_file(
            "Petição.pdf", b"%PDF", "application/pdf", "folder-1"
        )
        assert file_id == "new-file"
        kwargs = service.files.return_value.create.call_args.kwargs
        assert kwargs["body"] == {"name": "Petição.pdf", "parents": ["folder-1"]}
        service.permissions.assert_not_called()

    def test_trash_marks_file_as_trashed(self):
        service = MagicMock()
        client_with_service(service).trash_file("file-1")
        service.files.return_value.update.assert_called_once_with(
            fileId="file-1", body={"trashed": True}
        )

    @pytest.mark.parametrize(
        ("metadata", "expected"),
        [({"id": "f", "trashed": False}, True), ({"id": "f", "trashed": True}, False)],
    )
    def test_folder_exists_ignores_trashed(self, metadata, expected):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = metadata
        assert client_with_service(service).folder_exists("f") is expected

    def test_folder_exists_is_false_when_not_found(self):
        client = client_with_responses(({"status": "404"}, b"{}"))
        assert client.folder_exists("gone") is False


class TestFakeDriveClient:
    def test_trash_hides_folder_from_folder_exists(self):
        fake = FakeDriveClient()
        folder = fake.create_folder("Pasta", None)
        assert fake.folder_exists(folder) is True
        fake.trash_file(folder)
        assert fake.folder_exists(folder) is False

    def test_folder_inside_trashed_folder_is_trashed(self):
        fake = FakeDriveClient()
        root = fake.create_folder("Raiz", None)
        child = fake.create_folder("Filha", root)
        fake.trash_file(root)
        assert fake.folder_exists(child) is False

    def test_upload_and_download_roundtrip(self):
        fake = FakeDriveClient()
        folder = fake.create_folder("Pasta", None)
        file_id = fake.upload_file("a.pdf", b"conteudo", "application/pdf", folder)
        assert fake.download_file(file_id) == b"conteudo"
        assert fake.files[file_id] == ("a.pdf", b"conteudo", "application/pdf", folder)

    def test_download_missing_raises_not_found(self):
        with pytest.raises(DriveNotFoundError):
            FakeDriveClient().download_file("missing")

    def test_raise_on_next(self):
        fake = FakeDriveClient()
        fake.raise_on_next = DriveApiError(500, "boom")
        with pytest.raises(DriveApiError):
            fake.create_folder("Pasta", None)
        assert fake.create_folder("Pasta", None)
