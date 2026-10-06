import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import filetype
from fastapi import UploadFile

from app.shared.exceptions import (
    FileTooLargeError,
    InvalidMimeTypeError,
    ProcessDocumentNotFoundError,
)

_CHUNK_SIZE = 64 * 1024
_STORED_NAME_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[a-z0-9]+$"
)


@dataclass(frozen=True)
class StoredFile:
    stored_name: str
    mime_type: str
    size_bytes: int


class DocumentStorage(Protocol):
    def save(self, file: UploadFile) -> StoredFile: ...

    def path_for(self, stored_name: str) -> Path: ...

    def delete(self, stored_name: str) -> None: ...


class LocalDocumentStorage:
    def __init__(
        self,
        base_dir: str | Path,
        max_size_mb: int,
        allowed_mime_types: list[str],
    ) -> None:
        self.base_dir = Path(base_dir)
        self.max_size_mb = max_size_mb
        self.allowed_mime_types = allowed_mime_types
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file: UploadFile) -> StoredFile:
        max_bytes = self.max_size_mb * 1024 * 1024

        declared_size = getattr(file, "size", None)
        if declared_size is not None and declared_size > max_bytes:
            raise FileTooLargeError(self.max_size_mb)

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = file.file.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise FileTooLargeError(self.max_size_mb)
            chunks.append(chunk)
        content = b"".join(chunks)

        kind = filetype.guess(content) if content else None
        mime = kind.mime if kind else None
        if mime not in self.allowed_mime_types:
            raise InvalidMimeTypeError(self.allowed_mime_types)

        stored_name = f"{uuid.uuid4()}.{kind.extension}"
        (self.base_dir / stored_name).write_bytes(content)
        return StoredFile(stored_name=stored_name, mime_type=mime, size_bytes=total)

    def path_for(self, stored_name: str) -> Path:
        if not _STORED_NAME_PATTERN.match(stored_name):
            raise ProcessDocumentNotFoundError()

        base = self.base_dir.resolve()
        candidate = (base / stored_name).resolve()
        if not candidate.is_relative_to(base) or not candidate.is_file():
            raise ProcessDocumentNotFoundError()
        return candidate

    def delete(self, stored_name: str) -> None:
        if not _STORED_NAME_PATTERN.match(stored_name):
            return
        (self.base_dir / stored_name).unlink(missing_ok=True)
