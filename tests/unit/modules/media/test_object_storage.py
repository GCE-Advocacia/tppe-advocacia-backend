from uuid import uuid4

import boto3
import pytest
from moto import mock_aws

from app.config.settings import get_settings
from app.modules.media.storage import object_storage
from app.modules.media.storage.object_storage import (
    CACHE_CONTROL,
    LocalObjectStorage,
    S3ObjectStorage,
    get_object_storage,
)
from app.shared.exceptions import MediaNotFoundError

BASE_URL = "https://bucket.test/uploads"
INVALID_KEYS = [
    "../secret.env",
    "logos/../secret.env",
    "/etc/passwd",
    "photo.jpg",
    "other/12345678-1234-1234-1234-123456789012.jpg",
    "12345678-1234-1234-1234-123456789012",
    "12345678-1234-1234-1234-123456789012.JPG",
]


def new_key(prefix=""):
    return f"{prefix}{uuid4()}.png"


class TestPublicUrls:
    def test_url_and_key_roundtrip(self, tmp_path):
        storage = LocalObjectStorage(tmp_path, BASE_URL + "/")
        key = new_key("logos/")
        assert storage.url(key) == f"{BASE_URL}/{key}"
        assert storage.key_from_url(storage.url(key)) == key

    @pytest.mark.parametrize(
        "url",
        [
            None,
            f"https://other.test/uploads/{uuid4()}.png",
            f"{BASE_URL}/../{uuid4()}.png",
            f"{BASE_URL}/logos/../{uuid4()}.png",
            f"{BASE_URL}-evil/{uuid4()}.png",
            "http://localhost:8000/api/v1/media/logos/x.png",
        ],
    )
    def test_foreign_or_invalid_urls_have_no_key(self, tmp_path, url):
        storage = LocalObjectStorage(tmp_path, BASE_URL)
        assert storage.key_from_url(url or "") is None


class TestLocalObjectStorage:
    @pytest.fixture
    def storage(self, tmp_path):
        return LocalObjectStorage(tmp_path, BASE_URL)

    def test_put_read_and_delete(self, storage, tmp_path):
        key = new_key("logos/")
        storage.put(key, b"png", "image/png")
        path = storage.path_for(key)
        assert path == (tmp_path / key).resolve()
        assert path.read_bytes() == b"png"
        storage.delete(key)
        assert not path.exists()

    def test_put_never_overwrites(self, storage):
        key = new_key()
        storage.put(key, b"first", "image/png")
        with pytest.raises(FileExistsError):
            storage.put(key, b"second", "image/png")
        assert storage.path_for(key).read_bytes() == b"first"

    @pytest.mark.parametrize("key", INVALID_KEYS)
    def test_rejects_invalid_keys(self, storage, tmp_path, key):
        secret = tmp_path.parent / "secret.env"
        secret.write_bytes(b"JWT_SECRET_KEY=leaked")
        with pytest.raises(ValueError):
            storage.put(key, b"x", "image/png")
        with pytest.raises(MediaNotFoundError):
            storage.path_for(key)
        storage.delete(key)
        assert secret.read_bytes() == b"JWT_SECRET_KEY=leaked"

    def test_ignores_symlinks(self, storage, tmp_path):
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"unrelated")
        key = new_key("logos/")
        (tmp_path / "logos").mkdir()
        (tmp_path / key).symlink_to(outside)
        with pytest.raises(MediaNotFoundError):
            storage.path_for(key)
        storage.delete(key)
        assert outside.read_bytes() == b"unrelated"

    def test_missing_file_is_not_found(self, storage):
        with pytest.raises(MediaNotFoundError):
            storage.path_for(new_key())


class TestS3ObjectStorage:
    @pytest.fixture
    def s3(self):
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="uploads")
            yield client

    @pytest.fixture
    def storage(self, s3):
        return S3ObjectStorage(s3, "uploads", BASE_URL)

    def test_put_sets_content_type_and_cache_headers(self, storage, s3):
        key = new_key("logos/")
        storage.put(key, b"png", "image/png")
        obj = s3.get_object(Bucket="uploads", Key=key)
        assert obj["Body"].read() == b"png"
        assert obj["ContentType"] == "image/png"
        assert obj["CacheControl"] == CACHE_CONTROL

    def test_delete_removes_object(self, storage, s3):
        key = new_key()
        storage.put(key, b"png", "image/png")
        storage.delete(key)
        assert s3.list_objects_v2(Bucket="uploads").get("KeyCount") == 0

    @pytest.mark.parametrize("key", INVALID_KEYS)
    def test_rejects_invalid_keys(self, storage, s3, key):
        with pytest.raises(ValueError):
            storage.put(key, b"x", "image/png")
        storage.delete(key)
        assert s3.list_objects_v2(Bucket="uploads").get("KeyCount") == 0


class TestFactory:
    def test_uses_local_disk_without_bucket(self, monkeypatch, tmp_path):
        settings = get_settings()
        monkeypatch.setattr(settings, "media_bucket", "")
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
        storage = get_object_storage()
        assert isinstance(storage, LocalObjectStorage)
        assert storage.base_dir == tmp_path.resolve()

    def test_uses_bucket_when_configured(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "media_bucket", "uploads")
        monkeypatch.setattr(settings, "media_public_base_url", BASE_URL)
        monkeypatch.setattr(settings, "s3_endpoint_url", "https://s3.test")
        object_storage._s3_client.cache_clear()
        try:
            storage = get_object_storage()
            assert isinstance(storage, S3ObjectStorage)
            assert storage.bucket == "uploads"
            assert storage.url("x") == f"{BASE_URL}/x"
            assert storage.client.meta.endpoint_url == "https://s3.test"
        finally:
            object_storage._s3_client.cache_clear()
