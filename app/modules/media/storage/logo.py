import logging
import re
from uuid import uuid4

from app.modules.media.storage.object_storage import ObjectStorage, get_object_storage

logger = logging.getLogger(__name__)
_KEY_PATTERN = re.compile(
    r"logos/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.png"
)


class LogoStorage:
    """Only manages generated logos, isolated from ordinary uploaded media."""

    def __init__(self, storage: ObjectStorage | None = None) -> None:
        self.storage = storage or get_object_storage()

    def url(self, key: str) -> str:
        return self.storage.url(key)

    def save(self, content: bytes) -> str:
        key = f"logos/{uuid4()}.png"
        self.storage.put(key, content, "image/png")
        return key

    def delete(self, key: str) -> None:
        if not _KEY_PATTERN.fullmatch(key):
            return
        try:
            self.storage.delete(key)
        except Exception:
            # Cleanup must not report failure after a successful database commit,
            # or hide the original exception when rolling back a failed upload.
            logger.warning("Could not remove obsolete logo %s", key, exc_info=True)

    def delete_url(self, url: str | None) -> None:
        if url:
            key = self.storage.key_from_url(url)
            if key:
                self.delete(key)
