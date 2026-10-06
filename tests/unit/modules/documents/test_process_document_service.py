from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.modules.documents.model import ProcessDocument
from app.modules.documents.service import (
    ProcessDocumentService,
    sanitize_original_name,
)
from app.modules.documents.storage import StoredFile
from app.modules.users.model import User
from app.shared.exceptions import (
    ForbiddenError,
    ProcessDocumentNotFoundError,
    ProcessNotFoundError,
)
from app.shared.types import Role

STORED = StoredFile(
    stored_name="11111111-1111-1111-1111-111111111111.pdf",
    mime_type="application/pdf",
    size_bytes=123,
)


def make_user(user_id: int = 5, role: Role = Role.USER) -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.role = role
    return user


def make_document(uploaded_by: int | None = 5) -> ProcessDocument:
    document = MagicMock(spec=ProcessDocument)
    document.id = 10
    document.process_id = 1
    document.stored_name = STORED.stored_name
    document.uploaded_by = uploaded_by
    return document


def make_upload(filename: str | None = "peticao.pdf"):
    upload = MagicMock()
    upload.filename = filename
    return upload


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def process_repo():
    repository = MagicMock()
    repository.get_by_id.return_value = MagicMock()
    return repository


@pytest.fixture
def storage():
    mock = MagicMock()
    mock.save.return_value = STORED
    return mock


@pytest.fixture
def service(repo, process_repo, storage):
    return ProcessDocumentService(repo, process_repo, storage)


class TestSanitizeOriginalName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("peticao.pdf", "peticao.pdf"),
            ("  contrato.docx  ", "contrato.docx"),
            ("../../etc/passwd.pdf", "passwd.pdf"),
            ("C:\\Users\\ana\\procuracao.pdf", "procuracao.pdf"),
            ("petição inicial.pdf", "petição inicial.pdf"),
            ("nome\x00com\ncontrole.pdf", "nomecomcontrole.pdf"),
            ("", "documento"),
            (None, "documento"),
            ("../", "documento"),
            ("..", "documento"),
        ],
    )
    def test_cases(self, raw, expected):
        assert sanitize_original_name(raw) == expected

    def test_truncates_to_255_chars(self):
        assert len(sanitize_original_name("a" * 300 + ".pdf")) == 255


class TestUpload:
    def test_raises_when_process_missing(self, service, process_repo, storage):
        process_repo.get_by_id.return_value = None

        with pytest.raises(ProcessNotFoundError):
            service.upload(99, make_upload(), current_user=make_user())

        storage.save.assert_not_called()

    def test_persists_metadata(self, service, repo):
        created = make_document()
        repo.create.return_value = created

        result = service.upload(
            1, make_upload("../segredo/peticao.pdf"), current_user=make_user(7)
        )

        assert result is created
        repo.create.assert_called_once_with(
            process_id=1,
            original_name="peticao.pdf",
            stored_name=STORED.stored_name,
            mime_type="application/pdf",
            size_bytes=123,
            uploaded_by=7,
        )

    def test_upload_removes_file_when_db_fails(self, service, repo, storage):
        repo.create.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError):
            service.upload(1, make_upload(), current_user=make_user())

        storage.delete.assert_called_once_with(STORED.stored_name)


class TestListDocuments:
    def test_raises_when_process_missing(self, service, process_repo):
        process_repo.get_by_id.return_value = None

        with pytest.raises(ProcessNotFoundError):
            service.list_documents(99)

    def test_delegates_to_repository(self, service, repo):
        repo.list_by_process.return_value = ([], 0)

        assert service.list_documents(1, page=2, limit=5) == ([], 0)
        repo.list_by_process.assert_called_once_with(process_id=1, page=2, limit=5)


class TestGetDownload:
    def test_raises_when_document_missing(self, service, repo):
        repo.get_by_id.return_value = None

        with pytest.raises(ProcessDocumentNotFoundError):
            service.get_download(1, 10)

    def test_looks_up_document_within_process(self, service, repo, storage):
        document = make_document()
        repo.get_by_id.return_value = document
        storage.path_for.return_value = Path("/tmp/x.pdf")

        assert service.get_download(1, 10) == (document, Path("/tmp/x.pdf"))
        repo.get_by_id.assert_called_once_with(document_id=10, process_id=1)
        storage.path_for.assert_called_once_with(STORED.stored_name)


class TestDelete:
    def test_forbidden_for_other_user(self, service, repo, storage):
        repo.get_by_id.return_value = make_document(uploaded_by=5)

        with pytest.raises(ForbiddenError):
            service.delete(1, 10, current_user=make_user(8))

        repo.delete.assert_not_called()
        storage.delete.assert_not_called()

    def test_uploader_can_delete(self, service, repo, storage):
        document = make_document(uploaded_by=5)
        repo.get_by_id.return_value = document

        service.delete(1, 10, current_user=make_user(5))

        repo.delete.assert_called_once_with(document)
        storage.delete.assert_called_once_with(STORED.stored_name)

    def test_admin_can_delete_document_of_removed_user(self, service, repo, storage):
        document = make_document(uploaded_by=None)
        repo.get_by_id.return_value = document

        service.delete(1, 10, current_user=make_user(1, Role.ADMIN))

        repo.delete.assert_called_once_with(document)
        storage.delete.assert_called_once_with(STORED.stored_name)
