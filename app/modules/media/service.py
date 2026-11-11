from io import BytesIO
from uuid import uuid4

import filetype
from fastapi import UploadFile
from PIL import Image, ImageOps

from app.config.settings import get_settings
from app.modules.media.schema import MediaUploadResponse
from app.modules.media.storage.object_storage import ObjectStorage
from app.shared.exceptions import FileTooLargeError, InvalidMimeTypeError

_CHUNK_SIZE = 64 * 1024
MAX_IMAGE_DIMENSION = 1920
_PILLOW_FORMATS = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}


def _read_limited(file: UploadFile, max_size_mb: int) -> bytes:
    max_bytes = max_size_mb * 1024 * 1024

    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > max_bytes:
        raise FileTooLargeError(max_size_mb)

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(max_size_mb)
        chunks.append(chunk)
    return b"".join(chunks)


def optimize_image(content: bytes, extension: str, allowed: list[str]) -> bytes:
    """Reduz para no máximo MAX_IMAGE_DIMENSION px e regrava a imagem.

    Regravar também descarta metadados como EXIF (que pode conter GPS).
    Formatos sem otimização (ex.: GIF) são mantidos como vieram.
    """
    fmt = _PILLOW_FORMATS.get(extension)
    if fmt is None:
        return content
    try:
        with Image.open(BytesIO(content), formats=[fmt]) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
            output = BytesIO()
            if fmt == "JPEG":
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(output, "JPEG", quality=85, optimize=True, progressive=True)
            elif fmt == "PNG":
                image.save(output, "PNG", optimize=True)
            else:
                image.save(output, "WEBP", quality=85)
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidMimeTypeError(allowed) from exc
    return output.getvalue()


class MediaService:
    def __init__(self, storage: ObjectStorage) -> None:
        self.storage = storage
        self.settings = get_settings()

    def upload(self, file: UploadFile) -> MediaUploadResponse:
        allowed = self.settings.allowed_mime_types
        content = _read_limited(file, self.settings.max_file_size_mb)

        kind = filetype.guess(content)
        if kind is None or kind.mime not in allowed:
            raise InvalidMimeTypeError(allowed)

        content = optimize_image(content, kind.extension, allowed)
        key = f"{uuid4()}.{kind.extension}"
        self.storage.put(key, content, kind.mime)
        return MediaUploadResponse(url=self.storage.url(key))
