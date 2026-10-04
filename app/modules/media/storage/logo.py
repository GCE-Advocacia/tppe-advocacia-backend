import logging
import re
from pathlib import Path
from uuid import uuid4

from app.config.settings import get_settings
from app.shared.exceptions import MediaNotFoundError

logger = logging.getLogger(__name__)
_FILENAME_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.png"
)


class LogoStorage:
    """Only manages generated logos, isolated from ordinary uploaded media."""

    def __init__(self) -> None:
        self.directory = (Path(get_settings().upload_dir) / "logos").resolve()

    @staticmethod
    def url(filename: str, base_url: str) -> str:
        return f"{base_url.rstrip('/')}/api/v1/media/logos/{filename}"

    def save(self, content: bytes) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4()}.png"
        path = self.directory / filename
        try:
            with path.open("xb") as target:
                target.write(content)
        except OSError:
            self.delete(filename)
            raise
        return filename

    def get_file_path(self, filename: str) -> Path:
        if not _FILENAME_PATTERN.fullmatch(filename):
            raise MediaNotFoundError()
        path = self.directory / filename
        if path.is_symlink() or not path.is_file():
            raise MediaNotFoundError()
        return path

    def delete(self, filename: str) -> None:
        if not _FILENAME_PATTERN.fullmatch(filename):
            return
        path = self.directory / filename
        if path.is_symlink():
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # Cleanup must not report failure after a successful database commit,
            # or hide the original exception when rolling back a failed upload.
            logger.warning("Could not remove obsolete logo %s", filename, exc_info=True)

    def delete_url(self, url: str | None, base_url: str) -> None:
        if url:
            prefix = self.url("", base_url)
            if url.startswith(prefix):
                self.delete(url[len(prefix) :])
