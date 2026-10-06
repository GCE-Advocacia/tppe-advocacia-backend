import io

import bcrypt
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.main import app
from app.modules.clients.model import Client
from app.modules.clients.repository import ClientRepository
from app.modules.documents.deps import get_document_storage
from app.modules.documents.model import ProcessDocument
from app.modules.documents.storage import LocalDocumentStorage
from app.modules.processes.model import Process
from app.modules.processes.repository import ProcessRepository
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.types import Role

PDF_BYTES = b"%PDF-1.4\n" + b"0" * 200
ALLOWED = [
    "application/pdf",
    "image/png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]


@pytest.fixture(autouse=True)
def storage(tmp_path):
    local = LocalDocumentStorage(
        base_dir=tmp_path, max_size_mb=1, allowed_mime_types=ALLOWED
    )
    app.dependency_overrides[get_document_storage] = lambda: local
    yield local
    app.dependency_overrides.pop(get_document_storage, None)


@pytest.fixture
def created_process_ids(db_session: Session):
    ids: list[int] = []
    yield ids
    db_session.rollback()
    db_session.execute(
        delete(ProcessDocument).where(ProcessDocument.process_id.in_(ids))
    )
    db_session.execute(delete(Process).where(Process.id.in_(ids)))
    db_session.commit()


@pytest.fixture
def created_client_ids(db_session: Session):
    ids: list[int] = []
    yield ids
    db_session.execute(delete(Client).where(Client.id.in_(ids)))
    db_session.commit()


def _make_process(db_session, created_client_ids, created_process_ids, suffix: str):
    client = ClientRepository(db_session).create(
        name=f"Cliente Docs E2E {suffix}", cpf=f"5556667770{suffix}"
    )
    created_client_ids.append(client.id)
    process = ProcessRepository(db_session).create(
        number=f"1234567892024826550{suffix}",
        client_id=client.id,
        court="TJSP",
        action_type="Ação Cível",
    )
    db_session.commit()
    created_process_ids.append(process.id)
    return process


@pytest.fixture
def process_fixture(db_session, created_client_ids, created_process_ids):
    return _make_process(db_session, created_client_ids, created_process_ids, "1")


@pytest.fixture
def other_process(db_session, created_client_ids, created_process_ids):
    return _make_process(db_session, created_client_ids, created_process_ids, "2")


@pytest.fixture
def other_user_headers(client, db_session: Session):
    password = "Valid@1234"
    user = UserRepository(db_session).create(
        name="Other Docs User",
        email="e2e_docs_other@test.com",
        hashed_password=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        role=Role.USER,
    )
    db_session.commit()
    user_id = user.id
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "e2e_docs_other@test.com", "password": password},
    )
    yield {"Authorization": f"Bearer {response.json()['data']['access_token']}"}
    db_session.rollback()
    db_session.execute(delete(User).where(User.id == user_id))
    db_session.commit()


def _url(process_id: int) -> str:
    return f"/api/v1/processes/{process_id}/documents"


def _upload(
    client,
    headers,
    process_id: int,
    name: str = "peticao.pdf",
    content: bytes = PDF_BYTES,
):
    return client.post(
        _url(process_id),
        files={"file": (name, io.BytesIO(content), "application/pdf")},
        headers=headers,
    )


class TestUpload:
    def test_returns_401_without_token(self, client, process_fixture):
        response = _upload(client, {}, process_fixture.id)

        assert response.status_code == 401

    def test_returns_404_when_process_missing(self, client, user_headers):
        response = _upload(client, user_headers, 999999)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROCESS_NOT_FOUND"

    def test_returns_422_without_file(self, client, user_headers, process_fixture):
        response = client.post(_url(process_fixture.id), headers=user_headers)

        assert response.status_code == 422

    def test_creates_document(
        self, client, user_headers, active_user, process_fixture, storage
    ):
        response = _upload(client, user_headers, process_fixture.id)

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["process_id"] == process_fixture.id
        assert data["original_name"] == "peticao.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["size_bytes"] == len(PDF_BYTES)
        assert data["uploaded_by"] == active_user["id"]
        assert data["uploaded_by_name"] == "Active User"
        assert "stored_name" not in data
        assert len(list(storage.base_dir.iterdir())) == 1

    def test_strips_path_from_original_name(
        self, client, user_headers, process_fixture
    ):
        response = _upload(
            client, user_headers, process_fixture.id, name="../../etc/passwd.pdf"
        )

        assert response.status_code == 201
        assert response.json()["data"]["original_name"] == "passwd.pdf"

    def test_returns_415_for_disallowed_type(
        self, client, user_headers, process_fixture, storage
    ):
        response = _upload(
            client, user_headers, process_fixture.id, name="nota.pdf", content=b"oi"
        )

        assert response.status_code == 415
        assert response.json()["error"]["code"] == "INVALID_MIME_TYPE"
        assert list(storage.base_dir.iterdir()) == []

    def test_returns_413_when_too_large(self, client, user_headers, process_fixture):
        big = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)

        response = _upload(client, user_headers, process_fixture.id, content=big)

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


class TestList:
    def test_returns_401_without_token(self, client, process_fixture):
        assert client.get(_url(process_fixture.id)).status_code == 401

    def test_returns_404_when_process_missing(self, client, user_headers):
        response = client.get(_url(999999), headers=user_headers)

        assert response.status_code == 404

    def test_lists_only_documents_of_the_process_newest_first(
        self, client, user_headers, process_fixture, other_process
    ):
        first = _upload(client, user_headers, process_fixture.id, name="a.pdf")
        second = _upload(client, user_headers, process_fixture.id, name="b.pdf")
        _upload(client, user_headers, other_process.id, name="outro.pdf")

        response = client.get(_url(process_fixture.id), headers=user_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 2
        assert [d["id"] for d in body["data"]] == [
            second.json()["data"]["id"],
            first.json()["data"]["id"],
        ]


class TestDownload:
    def test_returns_401_without_token(self, client, user_headers, process_fixture):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]

        response = client.get(f"{_url(process_fixture.id)}/{doc_id}/download")

        assert response.status_code == 401

    def test_returns_file_with_original_name(
        self, client, user_headers, process_fixture
    ):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]

        response = client.get(
            f"{_url(process_fixture.id)}/{doc_id}/download", headers=user_headers
        )

        assert response.status_code == 200
        assert response.content == PDF_BYTES
        assert response.headers["content-type"] == "application/pdf"
        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="peticao.pdf"'
        )

    def test_encodes_non_ascii_name(self, client, user_headers, process_fixture):
        doc_id = _upload(
            client, user_headers, process_fixture.id, name="petição inicial.pdf"
        ).json()["data"]["id"]

        response = client.get(
            f"{_url(process_fixture.id)}/{doc_id}/download", headers=user_headers
        )

        assert response.status_code == 200
        assert (
            "peti%C3%A7%C3%A3o%20inicial.pdf"
            in (response.headers["content-disposition"])
        )

    def test_returns_404_when_document_belongs_to_other_process(
        self, client, user_headers, process_fixture, other_process
    ):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]

        response = client.get(
            f"{_url(other_process.id)}/{doc_id}/download", headers=user_headers
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROCESS_DOCUMENT_NOT_FOUND"

    def test_returns_404_when_file_missing_on_disk(
        self, client, user_headers, process_fixture, storage, db_session
    ):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]
        stored_name = db_session.get(ProcessDocument, doc_id).stored_name
        (storage.base_dir / stored_name).unlink()

        response = client.get(
            f"{_url(process_fixture.id)}/{doc_id}/download", headers=user_headers
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROCESS_DOCUMENT_NOT_FOUND"


class TestDelete:
    def test_returns_401_without_token(self, client, user_headers, process_fixture):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]

        response = client.delete(f"{_url(process_fixture.id)}/{doc_id}")

        assert response.status_code == 401

    def test_uploader_deletes_document_and_file(
        self, client, user_headers, process_fixture, storage
    ):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]

        response = client.delete(
            f"{_url(process_fixture.id)}/{doc_id}", headers=user_headers
        )

        assert response.status_code == 204
        assert list(storage.base_dir.iterdir()) == []
        download = client.get(
            f"{_url(process_fixture.id)}/{doc_id}/download", headers=user_headers
        )
        assert download.status_code == 404

    def test_other_user_gets_403(
        self, client, user_headers, other_user_headers, process_fixture, storage
    ):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]

        response = client.delete(
            f"{_url(process_fixture.id)}/{doc_id}", headers=other_user_headers
        )

        assert response.status_code == 403
        assert len(list(storage.base_dir.iterdir())) == 1

    def test_admin_can_delete(
        self, client, user_headers, admin_headers, process_fixture
    ):
        doc_id = _upload(client, user_headers, process_fixture.id).json()["data"]["id"]

        response = client.delete(
            f"{_url(process_fixture.id)}/{doc_id}", headers=admin_headers
        )

        assert response.status_code == 204

    def test_returns_404_for_unknown_document(
        self, client, user_headers, process_fixture
    ):
        response = client.delete(
            f"{_url(process_fixture.id)}/999999", headers=user_headers
        )

        assert response.status_code == 404
