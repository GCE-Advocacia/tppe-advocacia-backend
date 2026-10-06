"""Decode and normalize uploaded logos before they reach public storage."""

from io import BytesIO
from struct import error as StructError

import filetype
from fastapi import UploadFile
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from app.modules.media.svg import render_svg
from app.shared.exceptions import (
    FileTooLargeError,
    InvalidLogoImageError,
    InvalidMimeTypeError,
    LogoDimensionsTooLargeError,
)

MAX_LOGO_SIZE_MB = 5
MAX_LOGO_PIXELS = 20_000_000
MAX_LOGO_DIMENSION = 1024
LOGO_MIME_TYPES = ["image/png", "image/jpeg", "image/webp", "image/svg+xml"]
_FORMATS = ["PNG", "JPEG", "WEBP"]
_CHUNK_SIZE = 64 * 1024


def _read_upload(file: UploadFile) -> bytes:
    max_bytes = MAX_LOGO_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise FileTooLargeError(MAX_LOGO_SIZE_MB)

    content = bytearray()
    while chunk := file.file.read(_CHUNK_SIZE):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise FileTooLargeError(MAX_LOGO_SIZE_MB)
    return bytes(content)


def _to_srgb(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    profile = image.info.get("icc_profile")
    if profile:
        try:
            # Keep CMYK/gray profiles in their native mode until color conversion.
            source = (
                image
                if image.mode in {"RGB", "CMYK", "L", "LAB"}
                else image.convert("RGB")
            )
            rgb = ImageCms.profileToProfile(
                source,
                BytesIO(profile),
                ImageCms.createProfile("sRGB"),
                outputMode="RGB",
            )
            rgb.putalpha(rgba.getchannel("A"))
            return rgb
        except (ImageCms.PyCMSError, OSError, TypeError, ValueError):
            # A broken optional color profile should not prevent a valid logo.
            pass
    return rgba


def normalize_logo(file: UploadFile) -> bytes:
    content = _read_upload(file)
    kind = filetype.guess(content)
    if kind is None and (
        content.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")
        or file.content_type == "image/svg+xml"
        or (file.filename or "").lower().endswith(".svg")
    ):
        content = render_svg(content, MAX_LOGO_DIMENSION)
    elif kind is None or kind.mime not in [*LOGO_MIME_TYPES, "image/apng"]:
        raise InvalidMimeTypeError(LOGO_MIME_TYPES)

    try:
        with Image.open(BytesIO(content), formats=_FORMATS) as image:
            if image.width * image.height > MAX_LOGO_PIXELS:
                raise LogoDimensionsTooLargeError()
            image.verify()

        # verify() checks structure; load() also rejects incomplete pixel streams.
        with Image.open(BytesIO(content), formats=_FORMATS) as image:
            if getattr(image, "is_animated", False):
                raise InvalidLogoImageError()
            image.load()
            normalized = _to_srgb(ImageOps.exif_transpose(image))

        bounds = normalized.getchannel("A").getbbox()
        if bounds is None:
            raise InvalidLogoImageError()
        normalized = normalized.crop(bounds)
        normalized.thumbnail(
            (MAX_LOGO_DIMENSION, MAX_LOGO_DIMENSION), Image.Resampling.LANCZOS
        )

        # A fresh image discards EXIF, GPS, comments and all other source metadata.
        clean = Image.new("RGBA", normalized.size)
        clean.paste(normalized)
        output = BytesIO()
        clean.save(output, format="PNG", optimize=True)
        return output.getvalue()
    except Image.DecompressionBombError as exc:
        raise LogoDimensionsTooLargeError() from exc
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        StructError,
    ) as exc:
        raise InvalidLogoImageError() from exc


def normalize_favicon(file: UploadFile) -> bytes:
    """Fit the image in a transparent square without cropping or stretching it."""
    with Image.open(BytesIO(normalize_logo(file))) as source:
        image = source.convert("RGBA")
    # Fill the available icon area even for small source files. Padding a 32px
    # icon inside a 256px canvas would make it unreadable in the browser tab.
    scale = 256 / max(image.size)
    image = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    square = Image.new("RGBA", (256, 256))
    square.paste(image, ((256 - image.width) // 2, (256 - image.height) // 2))
    output = BytesIO()
    square.save(output, format="PNG", optimize=True)
    return output.getvalue()
