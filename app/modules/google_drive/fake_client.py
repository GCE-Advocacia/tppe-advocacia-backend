from uuid import uuid4

from app.modules.google_drive.client import DriveNotFoundError


class FakeDriveClient:
    """`DriveClient` em memória, usado nos testes."""

    def __init__(self) -> None:
        self.folders: dict[str, tuple[str, str | None]] = {}
        self.files: dict[str, tuple[str, bytes, str, str]] = {}
        self.trashed: set[str] = set()
        self.raise_on_next: Exception | None = None
        self.email: str | None = "escritorio@example.test"

    def _check(self) -> None:
        if self.raise_on_next is not None:
            exc, self.raise_on_next = self.raise_on_next, None
            raise exc

    def create_folder(self, name: str, parent_id: str | None) -> str:
        self._check()
        folder_id = f"folder-{uuid4().hex[:8]}"
        self.folders[folder_id] = (name, parent_id)
        return folder_id

    def folder_exists(self, folder_id: str) -> bool:
        self._check()
        # Como no Drive: o que está dentro de uma pasta na lixeira também está.
        current: str | None = folder_id
        while current is not None:
            if current not in self.folders or current in self.trashed:
                return False
            current = self.folders[current][1]
        return True

    def upload_file(
        self, name: str, content: bytes, mime_type: str, parent_id: str
    ) -> str:
        self._check()
        file_id = f"file-{uuid4().hex[:8]}"
        self.files[file_id] = (name, content, mime_type, parent_id)
        return file_id

    def download_file(self, file_id: str) -> bytes:
        self._check()
        if file_id not in self.files:
            raise DriveNotFoundError(file_id)
        return self.files[file_id][1]

    def trash_file(self, file_id: str) -> None:
        self._check()
        if file_id not in self.files and file_id not in self.folders:
            raise DriveNotFoundError(file_id)
        self.trashed.add(file_id)

    def get_email(self) -> str | None:
        self._check()
        return self.email
