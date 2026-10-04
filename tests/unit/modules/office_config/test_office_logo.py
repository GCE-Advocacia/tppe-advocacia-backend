from io import BytesIO
from struct import pack
from unittest.mock import MagicMock
from uuid import uuid4
from zlib import crc32

import pytest
from fastapi import UploadFile
from PIL import Image, ImageCms, PngImagePlugin

from app.config.settings import get_settings
from app.modules.media.logo import MAX_LOGO_SIZE_MB, normalize_favicon, normalize_logo
from app.modules.media.storage.logo import LogoStorage
from app.modules.office_config.model import OfficeConfig
from app.modules.office_config.service import OfficeConfigService
from app.shared.exceptions import (
    FileTooLargeError,
    InvalidLogoImageError,
    InvalidMimeTypeError,
    LogoDimensionsTooLargeError,
    MediaNotFoundError,
)


def encoded(image=None, fmt="PNG", **kwargs):
    image = image or Image.new("RGBA", (80, 40), (32, 64, 128, 128))
    stream = BytesIO()
    image.save(stream, format=fmt, **kwargs)
    return stream.getvalue()


def upload(content=None):
    return UploadFile(filename="logo.png", file=BytesIO(content or encoded()))


@pytest.fixture
def storage(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    return LogoStorage()


class TestLogoProcessing:
    @pytest.mark.parametrize("size", [(32, 16), (16, 32), (800, 400), (1, 300)])
    def test_favicon_uses_full_square_without_cropping_or_distortion(self, size):
        content = encoded(Image.new("RGBA", size, (20, 80, 140, 128)))
        result = Image.open(BytesIO(normalize_favicon(upload(content))))
        assert result.size == (256, 256)
        bounds = result.getchannel("A").getbbox()
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        assert max(width, height) == 256
        assert abs(width / 256 - size[0] / max(size)) < 0.005
        assert abs(height / 256 - size[1] / max(size)) < 0.005
        assert (
            result.getpixel((bounds[0] + width // 2, bounds[1] + height // 2))[3] == 128
        )

    def test_preserves_small_image_pixels_and_transparency_without_upscaling(self):
        result = Image.open(BytesIO(normalize_logo(upload())))
        assert result.format == "PNG"
        assert result.size == (80, 40)
        assert result.getpixel((5, 5)) == (32, 64, 128, 128)

    def test_shrinks_to_bound_without_distorting(self):
        source = Image.new("RGB", (2400, 1200), "red")
        result = Image.open(BytesIO(normalize_logo(upload(encoded(source)))))
        assert result.size == (1024, 512)

    def test_only_trims_fully_transparent_margins(self):
        source = Image.new("RGBA", (100, 70), (255, 255, 255, 0))
        source.paste((5, 10, 15, 1), (10, 20, 90, 60))
        result = Image.open(BytesIO(normalize_logo(upload(encoded(source)))))
        assert result.size == (80, 40)
        assert result.getpixel((0, 0)) == (5, 10, 15, 1)

    def test_palette_transparency_is_retained(self):
        source = Image.new("P", (30, 20), 0)
        source.putpalette([255, 0, 0, 0, 0, 255] + [0] * 762)
        source.putpixel((15, 10), 1)
        result = Image.open(
            BytesIO(normalize_logo(upload(encoded(source, transparency=1))))
        )
        assert result.getpixel((15, 10))[3] == 0
        assert result.size == (30, 20)

    def test_corrects_exif_orientation_and_strips_private_metadata(self):
        source = Image.new("RGB", (80, 40), "red")
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private source description"
        result = Image.open(
            BytesIO(normalize_logo(upload(encoded(source, "JPEG", exif=exif))))
        )
        assert result.size == (40, 80)
        assert not result.getexif()
        assert not result.info

    def test_normalizes_profile_and_removes_comments(self):
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Comment", "private comment")
        result = Image.open(
            BytesIO(
                normalize_logo(upload(encoded(icc_profile=profile, pnginfo=metadata)))
            )
        )
        assert result.getpixel((5, 5)) == (32, 64, 128, 128)
        assert not result.info

    def test_bad_optional_profile_does_not_break_valid_pixels(self):
        result = Image.open(
            BytesIO(normalize_logo(upload(encoded(icc_profile=b"broken"))))
        )
        assert result.getpixel((5, 5)) == (32, 64, 128, 128)
        assert not result.info

    @pytest.mark.parametrize("content", [b"not an image", b"<html></html>"])
    def test_rejects_unsupported_content(self, content):
        with pytest.raises(InvalidMimeTypeError):
            normalize_logo(upload(content))

    @pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
    def test_rejects_truncated_supported_image(self, fmt):
        content = encoded(Image.new("RGB", (80, 40), "red"), fmt)
        with pytest.raises(InvalidLogoImageError):
            normalize_logo(upload(content[: len(content) // 2]))

    def test_rejects_bad_png_checksum(self):
        content = bytearray(encoded())
        content[-8] ^= 1
        with pytest.raises(InvalidLogoImageError):
            normalize_logo(upload(bytes(content)))

    def test_rejects_pixel_bomb_before_decode(self):
        content = bytearray(encoded())
        content[16:24] = pack(">II", 5001, 4000)
        content[29:33] = pack(">I", crc32(content[12:29]))
        with pytest.raises(LogoDimensionsTooLargeError):
            normalize_logo(upload(bytes(content)))

    def test_rejects_transparent_only_image(self):
        with pytest.raises(InvalidLogoImageError):
            normalize_logo(upload(encoded(Image.new("RGBA", (10, 10)))))

    def test_rejects_animated_png(self):
        content = encoded(
            save_all=True,
            append_images=[Image.new("RGBA", (80, 40), "blue")],
            duration=100,
            loop=0,
        )
        with pytest.raises(InvalidLogoImageError):
            normalize_logo(upload(content))

    def test_enforces_real_size_even_when_declared_size_is_small(self):
        file = upload(b"x" * (MAX_LOGO_SIZE_MB * 1024 * 1024 + 1))
        file.size = 1
        with pytest.raises(FileTooLargeError):
            normalize_logo(file)

    def test_rejects_oversized_declared_size_without_reading(self):
        file = upload()
        file.size = MAX_LOGO_SIZE_MB * 1024 * 1024 + 1
        with pytest.raises(FileTooLargeError):
            normalize_logo(file)
        assert file.file.tell() == 0


class TestLogoStorage:
    def test_roundtrip_and_safe_deletion(self, storage):
        filename = storage.save(encoded())
        path = storage.get_file_path(filename)
        assert path.parent.name == "logos"
        assert path.read_bytes() == encoded()
        storage.delete_url(storage.url(filename, "http://api/"), "http://api/")
        assert not path.exists()

    def test_does_not_delete_general_media_or_foreign_urls(self, storage, tmp_path):
        filename = storage.save(encoded())
        general_media = tmp_path / filename
        general_media.write_bytes(b"unrelated")
        for url in (
            f"http://api/api/v1/media/{filename}",
            f"http://other/api/v1/media/logos/{filename}",
            f"http://api/api/v1/media/logos/../{filename}",
        ):
            storage.delete_url(url, "http://api/")
        assert general_media.read_bytes() == b"unrelated"
        assert storage.get_file_path(filename).is_file()

    def test_rejects_paths_and_symlinks_outside_logo_directory(self, storage, tmp_path):
        storage.directory.mkdir()
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"unrelated")
        filename = f"{uuid4()}.png"
        (storage.directory / filename).symlink_to(outside)
        for name in (filename, "../outside.png", "arbitrary.png"):
            with pytest.raises(MediaNotFoundError):
                storage.get_file_path(name)
            storage.delete(name)
        assert outside.read_bytes() == b"unrelated"

    def test_cleanup_error_is_logged_without_masking_commit_result(
        self, storage, monkeypatch, caplog
    ):
        filename = storage.save(encoded())

        def deny(*args, **kwargs):
            raise PermissionError("Cannot unlink")

        monkeypatch.setattr(type(storage.directory), "unlink", deny)
        storage.delete(filename)
        assert "Could not remove obsolete logo" in caplog.text


class TestLogoReplacement:
    @pytest.fixture
    def replacement(self, storage):
        filename = storage.save(encoded())
        old_url = storage.url(filename, "http://api/")
        repo = MagicMock()
        repo.get_config_for_update.return_value = OfficeConfig(id=1, logo_url=old_url)
        return OfficeConfigService(repo, storage), repo, filename, old_url

    @pytest.mark.parametrize("failure_point", ["flush", "commit"])
    def test_db_failure_preserves_old_file_and_cleans_new_one(
        self, replacement, storage, failure_point
    ):
        service, repo, old_filename, old_url = replacement
        if failure_point == "flush":
            repo.update_config.side_effect = RuntimeError("DB failed")
        else:
            repo.db.commit.side_effect = RuntimeError("DB failed")

        with pytest.raises(RuntimeError, match="DB failed"):
            service.update_logo(upload(), "http://api/")

        repo.db.rollback.assert_called_once()
        assert [p.name for p in storage.directory.iterdir()] == [old_filename]
        assert repo.get_config_for_update.return_value.logo_url == old_url

    def test_invalid_replacement_does_not_touch_database_or_storage(
        self, replacement, storage
    ):
        service, repo, old_filename, _ = replacement
        with pytest.raises(InvalidMimeTypeError):
            service.update_logo(upload(b"broken"), "http://api/")
        repo.get_config_for_update.assert_not_called()
        repo.update_config.assert_not_called()
        assert [p.name for p in storage.directory.iterdir()] == [old_filename]

    def test_storage_failure_does_not_touch_database(self, replacement, monkeypatch):
        service, repo, _, _ = replacement
        monkeypatch.setattr(
            service.logo_storage, "save", MagicMock(side_effect=OSError("disk full"))
        )
        with pytest.raises(OSError, match="disk full"):
            service.update_logo(upload(), "http://api/")
        repo.update_config.assert_not_called()
        repo.db.commit.assert_not_called()

    def test_old_file_is_kept_until_commit_then_removed(self, replacement, storage):
        service, repo, old_filename, _ = replacement

        def commit():
            assert storage.get_file_path(old_filename).is_file()
            assert len(list(storage.directory.iterdir())) == 2

        repo.db.commit.side_effect = commit
        service.update_logo(upload(), "http://api/")
        assert len(list(storage.directory.iterdir())) == 1
        assert not (storage.directory / old_filename).exists()
        assert repo.update_config.call_args.args[0]["logo_url"].startswith(
            "http://api/api/v1/media/logos/"
        )
