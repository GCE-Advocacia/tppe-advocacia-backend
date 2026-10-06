import io
import re
import zipfile
from unittest.mock import MagicMock

import pytest

from app.modules.documents.storage import LocalDocumentStorage
from app.shared.exceptions import (
    FileTooLargeError,
    InvalidMimeTypeError,
    ProcessDocumentNotFoundError,
)

PDF = "application/pdf"
PNG = "image/png"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

PDF_BYTES = b"%PDF-1.4\n" + b"0" * 100
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
EXE_BYTES = b"MZ" + b"\x00" * 100

_STORED_NAME = re.compile(r"^[0-9a-f-]{36}\.[a-z0-9]+$")


def docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


def make_upload_file(content: bytes, size: int | None = None):
    mock = MagicMock()
    mock.file = io.BytesIO(content)
    mock.size = size
    return mock


@pytest.fixture
def storage(tmp_path):
    return LocalDocumentStorage(
        base_dir=tmp_path, max_size_mb=1, allowed_mime_types=[PDF, PNG, DOCX]
    )


class TestSave:
    @pytest.mark.parametrize(
        ("content", "mime", "extension"),
        [
            (PDF_BYTES, PDF, "pdf"),
            (PNG_BYTES, PNG, "png"),
            (docx_bytes(), DOCX, "docx"),
        ],
    )
    def test_saves_allowed_types(self, storage, tmp_path, content, mime, extension):
        stored = storage.save(make_upload_file(content))

        assert stored.mime_type == mime
        assert stored.size_bytes == len(content)
        assert stored.stored_name.endswith(f".{extension}")
        assert _STORED_NAME.match(stored.stored_name)
        assert (tmp_path / stored.stored_name).read_bytes() == content

    def test_generates_unique_names(self, storage):
        first = storage.save(make_upload_file(PDF_BYTES))
        second = storage.save(make_upload_file(PDF_BYTES))

        assert first.stored_name != second.stored_name

    def test_rejects_executable_disguised_as_pdf(self, storage, tmp_path):
        with pytest.raises(InvalidMimeTypeError):
            storage.save(make_upload_file(EXE_BYTES))

        assert list(tmp_path.iterdir()) == []

    def test_rejects_plain_text(self, storage):
        with pytest.raises(InvalidMimeTypeError):
            storage.save(make_upload_file(b"apenas texto"))

    def test_rejects_empty_file(self, storage):
        with pytest.raises(InvalidMimeTypeError):
            storage.save(make_upload_file(b""))

    def test_rejects_declared_size_over_limit_without_reading(self, storage):
        file = make_upload_file(PDF_BYTES, size=2 * 1024 * 1024)

        with pytest.raises(FileTooLargeError):
            storage.save(file)

        assert file.file.tell() == 0

    def test_rejects_content_over_limit_when_size_unknown(self, storage, tmp_path):
        big = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)

        with pytest.raises(FileTooLargeError):
            storage.save(make_upload_file(big, size=None))

        assert list(tmp_path.iterdir()) == []


class TestPathFor:
    def test_returns_path_of_saved_file(self, storage, tmp_path):
        stored = storage.save(make_upload_file(PDF_BYTES))

        assert (
            storage.path_for(stored.stored_name)
            == (tmp_path / stored.stored_name).resolve()
        )

    @pytest.mark.parametrize(
        "name",
        ["../segredo.pdf", "..\\segredo.pdf", "nao-e-uuid.pdf", ""],
    )
    def test_rejects_invalid_names(self, storage, name):
        with pytest.raises(ProcessDocumentNotFoundError):
            storage.path_for(name)

    def test_rejects_missing_file(self, storage):
        with pytest.raises(ProcessDocumentNotFoundError):
            storage.path_for("00000000-0000-0000-0000-000000000000.pdf")


class TestDelete:
    def test_removes_file(self, storage, tmp_path):
        stored = storage.save(make_upload_file(PDF_BYTES))

        storage.delete(stored.stored_name)

        assert not (tmp_path / stored.stored_name).exists()

    def test_ignores_missing_file(self, storage):
        storage.delete("00000000-0000-0000-0000-000000000000.pdf")

    def test_ignores_invalid_name(self, storage, tmp_path):
        outside = tmp_path.parent / "fora.pdf"
        outside.write_bytes(PDF_BYTES)

        storage.delete("../fora.pdf")

        assert outside.exists()
        outside.unlink()
