import io

import pytest
from PIL import Image

from app.config.settings import get_settings
from app.modules.media.storage.object_storage import CACHE_CONTROL


def jpeg_bytes(size=(40, 20)):
    stream = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(stream, format="JPEG")
    return stream.getvalue()


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "media_bucket", "")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "max_file_size_mb", 1)
    monkeypatch.setattr(settings, "allowed_mime_types", ["image/jpeg", "image/png"])
    return tmp_path


@pytest.fixture
def jpeg_file():
    return ("file", ("photo.jpg", io.BytesIO(jpeg_bytes()), "image/jpeg"))


class TestUpload:
    def test_upload_without_token_returns_401(self, client, jpeg_file):
        response = client.post("/api/v1/media/upload", files=[jpeg_file])
        assert response.status_code == 401

    def test_upload_with_invalid_mime_returns_415(
        self, client, user_headers, media_dir
    ):
        pdf_content = b"%PDF-1.4" + b"\x00" * 100
        response = client.post(
            "/api/v1/media/upload",
            files=[("file", ("doc.pdf", io.BytesIO(pdf_content), "application/pdf"))],
            headers=user_headers,
        )
        assert response.status_code == 415
        assert response.json()["error"]["code"] == "INVALID_MIME_TYPE"
        assert not list(media_dir.iterdir())

    def test_upload_exceeding_size_returns_413(self, client, user_headers, media_dir):
        big = b"\x00" * (2 * 1024 * 1024)
        response = client.post(
            "/api/v1/media/upload",
            files=[("file", ("big.jpg", io.BytesIO(big), "image/jpeg"))],
            headers=user_headers,
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"

    def test_upload_valid_jpeg_returns_201_with_url(
        self, client, user_headers, media_dir, jpeg_file
    ):
        response = client.post(
            "/api/v1/media/upload", files=[jpeg_file], headers=user_headers
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        url = body["data"]["url"]
        assert url.startswith(get_settings().media_public_base_url + "/")
        assert url.endswith(".jpg")
        assert len(list(media_dir.iterdir())) == 1


class TestServeFile:
    def test_serves_uploaded_file_with_cache_headers(
        self, client, user_headers, media_dir, jpeg_file
    ):
        url = client.post(
            "/api/v1/media/upload", files=[jpeg_file], headers=user_headers
        ).json()["data"]["url"]
        key = url.rsplit("/", 1)[1]

        response = client.get(f"/api/v1/media/{key}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == CACHE_CONTROL
        assert response.content == next(media_dir.iterdir()).read_bytes()

    def test_serve_missing_file_returns_404(self, client, media_dir):
        response = client.get("/api/v1/media/12345678-1234-1234-1234-123456789012.jpg")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MEDIA_NOT_FOUND"

    def test_serve_rejects_invalid_filename_returns_404(self, client, media_dir):
        response = client.get("/api/v1/media/test.jpg")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MEDIA_NOT_FOUND"

    def test_serve_rejects_path_traversal_returns_404(self, client, media_dir):
        secret = media_dir.parent / "secret.env"
        secret.write_bytes(b"JWT_SECRET_KEY=leaked")
        response = client.get("/api/v1/media/..%2Fsecret.env")
        assert response.status_code == 404
        assert b"JWT_SECRET_KEY=leaked" not in response.content

    def test_route_is_disabled_when_using_bucket(self, client, media_dir, monkeypatch):
        name = "12345678-1234-1234-1234-123456789012.jpg"
        (media_dir / name).write_bytes(jpeg_bytes())
        monkeypatch.setattr(get_settings(), "media_bucket", "uploads")
        response = client.get(f"/api/v1/media/{name}")
        assert response.status_code == 404
