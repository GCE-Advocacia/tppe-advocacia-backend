import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.modules.media.schema import MediaUploadResponse
from app.modules.media.service import MAX_IMAGE_DIMENSION, MediaService
from app.shared.exceptions import FileTooLargeError, InvalidMimeTypeError

ALLOWED = ["image/jpeg", "image/png", "image/webp"]


def encoded(fmt="JPEG", size=(40, 20), mode="RGB", **kwargs):
    stream = io.BytesIO()
    Image.new(mode, size, (200, 100, 50)).save(stream, format=fmt, **kwargs)
    return stream.getvalue()


def make_upload_file(content: bytes, filename="photo.jpg", size: int | None = None):
    mock = MagicMock()
    mock.filename = filename
    mock.file = io.BytesIO(content)
    mock.size = size if size is not None else len(content)
    return mock


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key, content, content_type):
        self.objects[key] = (content, content_type)

    def url(self, key):
        return f"https://bucket.test/media/{key}"


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def service(storage, monkeypatch):
    service = MediaService(storage)
    monkeypatch.setattr(
        service, "settings", MagicMock(max_file_size_mb=1, allowed_mime_types=ALLOWED)
    )
    return service


def stored(storage):
    assert len(storage.objects) == 1
    key, (content, content_type) = next(iter(storage.objects.items()))
    return key, content, content_type


class TestUpload:
    def test_stores_image_and_returns_public_url(self, service, storage):
        result = service.upload(make_upload_file(encoded()))

        key, _, content_type = stored(storage)
        assert key.endswith(".jpg")
        assert content_type == "image/jpeg"
        assert result == MediaUploadResponse(url=f"https://bucket.test/media/{key}")

    def test_keys_are_unique(self, service, storage):
        service.upload(make_upload_file(encoded()))
        service.upload(make_upload_file(encoded()))
        assert len(storage.objects) == 2

    @pytest.mark.parametrize("filename", ["evil.html", "photo.jpg.php", "x"])
    def test_extension_comes_from_content_not_filename(
        self, service, storage, filename
    ):
        service.upload(make_upload_file(encoded("PNG"), filename))
        key, _, content_type = stored(storage)
        assert key.endswith(".png")
        assert content_type == "image/png"

    def test_rejects_file_too_large(self, service, storage):
        with pytest.raises(FileTooLargeError):
            service.upload(make_upload_file(b"\x00" * (2 * 1024 * 1024)))
        assert not storage.objects

    def test_rejects_oversize_via_declared_size_without_reading(self, service):
        file = make_upload_file(b"", size=5 * 1024 * 1024 * 1024)
        with pytest.raises(FileTooLargeError):
            service.upload(file)
        assert file.file.tell() == 0

    def test_rejects_oversize_when_size_attr_missing(self, service):
        file = make_upload_file(b"\x00" * (2 * 1024 * 1024))
        file.size = None
        with pytest.raises(FileTooLargeError):
            service.upload(file)

    def test_rejects_disallowed_mime_type(self, service, storage):
        with pytest.raises(InvalidMimeTypeError):
            service.upload(make_upload_file(b"%PDF-1.4" + b"\x00" * 100, "doc.pdf"))
        assert not storage.objects

    def test_rejects_undetectable_content(self, service, storage):
        with pytest.raises(InvalidMimeTypeError):
            service.upload(make_upload_file(b"random garbage", "file.xyz"))
        assert not storage.objects

    def test_rejects_corrupted_image_with_valid_magic_bytes(self, service, storage):
        fake_jpeg = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 100
        with pytest.raises(InvalidMimeTypeError):
            service.upload(make_upload_file(fake_jpeg))
        assert not storage.objects


class TestOptimization:
    @pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
    def test_large_images_are_reduced_keeping_aspect_ratio(self, service, storage, fmt):
        service.upload(make_upload_file(encoded(fmt, size=(4000, 2000))))
        _, content, _ = stored(storage)
        with Image.open(io.BytesIO(content)) as image:
            assert image.size == (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION // 2)
            assert image.format == fmt

    def test_small_images_are_not_upscaled(self, service, storage):
        service.upload(make_upload_file(encoded(size=(300, 200))))
        _, content, _ = stored(storage)
        with Image.open(io.BytesIO(content)) as image:
            assert image.size == (300, 200)

    def test_exif_metadata_is_removed(self, service, storage):
        exif = Image.Exif()
        exif[0x010F] = "Camera with GPS"
        service.upload(make_upload_file(encoded(exif=exif.tobytes())))
        _, content, _ = stored(storage)
        assert b"Camera with GPS" not in content

    def test_exif_orientation_is_applied(self, service, storage):
        exif = Image.Exif()
        exif[0x0112] = 6  # rotacionar 90 graus
        service.upload(make_upload_file(encoded(size=(40, 20), exif=exif.tobytes())))
        _, content, _ = stored(storage)
        with Image.open(io.BytesIO(content)) as image:
            assert image.size == (20, 40)

    def test_png_transparency_is_preserved(self, service, storage):
        service.upload(make_upload_file(encoded("PNG", mode="RGBA"), "logo.png"))
        _, content, _ = stored(storage)
        with Image.open(io.BytesIO(content)) as image:
            assert image.mode == "RGBA"
