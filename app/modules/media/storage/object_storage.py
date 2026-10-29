import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import boto3
from botocore.config import Config

from app.config.settings import get_settings
from app.shared.exceptions import MediaNotFoundError

# Nomes gerados pelo sistema: uuid4 + extensão, opcionalmente dentro de logos/.
# Qualquer outra chave é recusada, o que impede path traversal e o acesso a
# objetos que o sistema não criou.
_KEY_PATTERN = re.compile(
    r"(?:logos/)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[a-z0-9]+"
)

# Cada upload ganha uma chave nova, então o conteúdo de uma chave nunca muda.
CACHE_CONTROL = "public, max-age=31536000, immutable"


def is_valid_key(key: str) -> bool:
    return bool(_KEY_PATTERN.fullmatch(key))


class ObjectStorage(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def url(self, key: str) -> str: ...

    def key_from_url(self, url: str) -> str | None: ...


class _PublicUrls:
    def __init__(self, public_base_url: str) -> None:
        self.public_base_url = public_base_url.rstrip("/")

    def url(self, key: str) -> str:
        return f"{self.public_base_url}/{key}"

    def key_from_url(self, url: str) -> str | None:
        prefix = f"{self.public_base_url}/"
        if not url.startswith(prefix):
            return None
        key = url[len(prefix) :]
        return key if is_valid_key(key) else None


class S3ObjectStorage(_PublicUrls):
    """Bucket compatível com S3 (Neon Object Storage), com leitura pública."""

    def __init__(self, client, bucket: str, public_base_url: str) -> None:
        super().__init__(public_base_url)
        self.client = client
        self.bucket = bucket

    def put(self, key: str, content: bytes, content_type: str) -> None:
        if not is_valid_key(key):
            raise ValueError(f"Invalid media key: {key}")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            CacheControl=CACHE_CONTROL,
        )

    def delete(self, key: str) -> None:
        if is_valid_key(key):
            self.client.delete_object(Bucket=self.bucket, Key=key)


class LocalObjectStorage(_PublicUrls):
    """Disco local, usado só em desenvolvimento e testes (sem MEDIA_BUCKET)."""

    def __init__(self, base_dir: str | Path, public_base_url: str) -> None:
        super().__init__(public_base_url)
        self.base_dir = Path(base_dir).resolve()

    def put(self, key: str, content: bytes, content_type: str) -> None:
        if not is_valid_key(key):
            raise ValueError(f"Invalid media key: {key}")
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as target:
            try:
                target.write(content)
            except OSError:
                target.close()
                path.unlink(missing_ok=True)
                raise

    def delete(self, key: str) -> None:
        if not is_valid_key(key):
            return
        path = self.base_dir / key
        if not path.is_symlink():
            path.unlink(missing_ok=True)

    def path_for(self, key: str) -> Path:
        if not is_valid_key(key):
            raise MediaNotFoundError()
        path = self.base_dir / key
        if path.is_symlink() or not path.is_file():
            raise MediaNotFoundError()
        return path


@lru_cache(maxsize=1)
def _s3_client(endpoint_url: str, region: str, access_key_id: str, secret: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        region_name=region,
        aws_access_key_id=access_key_id or None,
        aws_secret_access_key=secret or None,
        config=Config(
            # O Neon exige path-style e não aceita os checksums que o botocore
            # passou a enviar por padrão.
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.media_bucket:
        client = _s3_client(
            settings.s3_endpoint_url,
            settings.s3_region,
            settings.s3_access_key_id,
            settings.s3_secret_access_key,
        )
        return S3ObjectStorage(
            client, settings.media_bucket, settings.media_public_base_url
        )
    return LocalObjectStorage(settings.upload_dir, settings.media_public_base_url)
