from urllib.parse import parse_qs, urlparse

import pytest

from app.config.settings import get_settings
from app.modules.clients.repository import ClientRepository
from app.modules.documents.model import ProcessDocument
from app.modules.external_api_logs.model import (
    ExternalApiLog,
    ExternalApiOperation,
    ExternalApiProvider,
)
from app.modules.google_calendar.oauth import GoogleOAuthFlow
from app.modules.google_drive.client import DriveApiError, DriveAuthRevokedError
from app.modules.google_drive.service import ROOT_FOLDER_NAME
from app.modules.processes.repository import ProcessRepository
from app.modules.processes.schema import format_cnj

NUMBER = "00012345620248260100"
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 100
DRIVE = "/api/v1/integrations/google-drive"


@pytest.fixture
def process_id(drive_api) -> int:
    with drive_api.session() as session:
        client = ClientRepository(session).create(name="Cliente", cpf="11122233355")
        process = ProcessRepository(session).create(
            number=NUMBER, client_id=client.id, court="TJSP", action_type="Cível"
        )
        session.commit()
        return process.id


@pytest.fixture
def connected(drive_api, monkeypatch):
    monkeypatch.setattr(
        GoogleOAuthFlow, "exchange_code", lambda self, code: ("refresh", "drive.file")
    )
    auth_url = drive_api.client.get(
        f"{DRIVE}/auth-url", headers=drive_api.headers(1)
    ).json()["data"]["auth_url"]
    state = parse_qs(urlparse(auth_url).query)["state"][0]
    drive_api.client.get(
        f"{DRIVE}/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )


def docs_url(process_id: int) -> str:
    return f"/api/v1/processes/{process_id}/documents"


def upload(api, process_id, name="Petição inicial.pdf", content=PDF_BYTES, user=1):
    return api.client.post(
        docs_url(process_id),
        files={"file": (name, content, "application/pdf")},
        headers=api.headers(user),
    )


def drive_logs(api) -> list[ExternalApiLog]:
    with api.session() as session:
        return (
            session.query(ExternalApiLog)
            .filter(ExternalApiLog.provider == ExternalApiProvider.GOOGLE_DRIVE)
            .all()
        )


def test_upload_without_connection_returns_409_not_connected(drive_api, process_id):
    response = upload(drive_api, process_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GOOGLE_DRIVE_NOT_CONNECTED"
    assert drive_api.fake.files == {}


def test_upload_list_download_delete_roundtrip(drive_api, process_id, connected):
    fake = drive_api.fake
    response = upload(drive_api, process_id)
    assert response.status_code == 201
    document_id = response.json()["data"]["id"]

    [(file_id, (name, content, mime, folder))] = fake.files.items()
    assert (name, content, mime) == (
        "Petição inicial.pdf",
        PDF_BYTES,
        "application/pdf",
    )
    assert fake.folders[folder][0] == format_cnj(NUMBER)
    assert fake.folders[fake.folders[folder][1]] == (ROOT_FOLDER_NAME, None)

    listed = drive_api.client.get(docs_url(process_id), headers=drive_api.headers(2))
    assert [d["id"] for d in listed.json()["data"]] == [document_id]

    downloaded = drive_api.client.get(
        f"{docs_url(process_id)}/{document_id}/download", headers=drive_api.headers(2)
    )
    assert downloaded.status_code == 200
    assert downloaded.content == PDF_BYTES
    assert downloaded.headers["content-type"] == "application/pdf"

    deleted = drive_api.client.delete(
        f"{docs_url(process_id)}/{document_id}", headers=drive_api.headers(1)
    )
    assert deleted.status_code == 204
    assert file_id in fake.trashed


def test_download_header_keeps_accented_name(drive_api, process_id, connected):
    document_id = upload(drive_api, process_id).json()["data"]["id"]
    response = drive_api.client.get(
        f"{docs_url(process_id)}/{document_id}/download", headers=drive_api.headers(1)
    )
    assert response.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''Peti%C3%A7%C3%A3o%20inicial.pdf"
    )


def test_upload_reuses_process_folder(drive_api, process_id, connected):
    upload(drive_api, process_id, name="a.pdf")
    upload(drive_api, process_id, name="b.pdf")
    assert len(drive_api.fake.folders) == 2
    assert len({file[3] for file in drive_api.fake.files.values()}) == 1


def test_db_failure_after_upload_trashes_drive_file(
    drive_api, process_id, connected, monkeypatch
):
    from app.modules.documents.repository import ProcessDocumentRepository

    def broken_create(self, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ProcessDocumentRepository, "create", broken_create)
    with pytest.raises(RuntimeError):
        upload(drive_api, process_id)
    [file_id] = drive_api.fake.files
    assert file_id in drive_api.fake.trashed


def test_drive_error_on_upload_returns_503_and_is_logged(
    drive_api, process_id, connected
):
    drive_api.fake.raise_on_next = DriveApiError(500, "boom")
    response = upload(drive_api, process_id)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GOOGLE_DRIVE_UNAVAILABLE"
    [log] = drive_logs(drive_api)
    assert log.operation == ExternalApiOperation.DOCUMENT_UPLOAD
    assert log.http_status == 500


def test_revoked_token_on_upload_disconnects_and_returns_409(
    drive_api, process_id, connected
):
    drive_api.fake.raise_on_next = DriveAuthRevokedError("invalid_grant")
    response = upload(drive_api, process_id)
    assert response.status_code == 409
    status = drive_api.client.get(f"{DRIVE}/status", headers=drive_api.headers(1))
    assert status.json()["data"]["connected"] is False


def test_invalid_type_is_rejected_before_calling_drive(
    drive_api, process_id, connected
):
    response = upload(drive_api, process_id, name="x.exe", content=b"MZ" + b"\0" * 64)
    assert response.status_code == 415
    assert drive_api.fake.files == {}
    assert drive_api.fake.folders == {}


def test_delete_still_succeeds_when_drive_fails_and_failure_is_logged(
    drive_api, process_id, connected
):
    document_id = upload(drive_api, process_id).json()["data"]["id"]
    drive_api.fake.raise_on_next = DriveApiError(503, "down")

    response = drive_api.client.delete(
        f"{docs_url(process_id)}/{document_id}", headers=drive_api.headers(1)
    )

    assert response.status_code == 204
    with drive_api.session() as session:
        assert session.get(ProcessDocument, document_id) is None
    [log] = drive_logs(drive_api)
    assert log.operation == ExternalApiOperation.DOCUMENT_DELETE


def test_download_of_file_missing_in_drive_returns_404(
    drive_api, process_id, connected
):
    document_id = upload(drive_api, process_id).json()["data"]["id"]
    drive_api.fake.files.clear()
    response = drive_api.client.get(
        f"{docs_url(process_id)}/{document_id}/download", headers=drive_api.headers(1)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROCESS_DOCUMENT_NOT_FOUND"


def test_local_document_still_downloads_and_deletes_with_drive_active(
    drive_api, process_id, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "document_storage", "local")
    document_id = upload(drive_api, process_id).json()["data"]["id"]
    monkeypatch.setattr(settings, "document_storage", "drive")

    response = drive_api.client.get(
        f"{docs_url(process_id)}/{document_id}/download", headers=drive_api.headers(1)
    )
    assert response.status_code == 200
    assert response.content == PDF_BYTES

    deleted = drive_api.client.delete(
        f"{docs_url(process_id)}/{document_id}", headers=drive_api.headers(1)
    )
    assert deleted.status_code == 204
    assert drive_api.fake.files == {}


def test_non_author_non_admin_cannot_delete(drive_api, process_id, connected):
    document_id = upload(drive_api, process_id, user=1).json()["data"]["id"]
    response = drive_api.client.delete(
        f"{docs_url(process_id)}/{document_id}", headers=drive_api.headers(2)
    )
    assert response.status_code == 403
    assert drive_api.fake.trashed == set()


def test_delete_while_disconnected_returns_409_and_keeps_document(
    drive_api, process_id, connected, monkeypatch
):
    from app.modules.google_drive import service

    monkeypatch.setattr(service, "revoke_refresh_token", lambda token: None)
    document_id = upload(drive_api, process_id).json()["data"]["id"]
    drive_api.client.delete(DRIVE, headers=drive_api.headers(1))

    response = drive_api.client.delete(
        f"{docs_url(process_id)}/{document_id}", headers=drive_api.headers(1)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GOOGLE_DRIVE_NOT_CONNECTED"
    with drive_api.session() as session:
        assert session.get(ProcessDocument, document_id) is not None
    assert drive_api.fake.trashed == set()


def test_download_while_disconnected_returns_409(
    drive_api, process_id, connected, monkeypatch
):
    from app.modules.google_drive import service

    monkeypatch.setattr(service, "revoke_refresh_token", lambda token: None)
    document_id = upload(drive_api, process_id).json()["data"]["id"]
    drive_api.client.delete(DRIVE, headers=drive_api.headers(1))

    response = drive_api.client.get(
        f"{docs_url(process_id)}/{document_id}/download", headers=drive_api.headers(1)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GOOGLE_DRIVE_NOT_CONNECTED"
