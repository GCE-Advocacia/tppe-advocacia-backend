"""Exercise logo HTTP routes with real auth, database transactions and local files."""

from io import BytesIO

import jwt
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings
from app.db.database import get_db
from app.main import app_exception_handler, validation_exception_handler
from app.modules.media.router import router as media_router
from app.modules.office_config.model import OfficeConfig
from app.modules.office_config.router import router as office_config_router
from app.modules.users.model import User
from app.shared.exceptions import AppException
from app.shared.types import Role

CONFIG_URL = "/api/v1/office-config"
LOGO_URL = f"{CONFIG_URL}/logo"
PREVIEW_URL = f"{LOGO_URL}/preview"


def image_bytes(format="PNG", size=(80, 40), color=(20, 80, 140, 128)):
    image = Image.new("RGBA", size, color)
    if format == "JPEG":
        image = image.convert("RGB")
    output = BytesIO()
    image.save(output, format=format)
    return output.getvalue()


@pytest.fixture
def logo_api(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OfficeConfig.__table__.create(engine)
    User.__table__.create(engine)
    with Session(engine) as session:
        session.add(OfficeConfig(id=1, differentials=[], areas_of_practice=[]))
        session.add_all(
            [
                User(
                    id=user_id,
                    name=f"User {user_id}",
                    email=f"logo-{user_id}@example.test",
                    hashed_password="unused",
                    role=role,
                    is_active=active,
                )
                for user_id, role, active in [
                    (1, Role.ADMIN, True),
                    (2, Role.USER, True),
                    (3, Role.ADMIN, False),
                ]
            ]
        )
        session.commit()

    def database():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(office_config_router, prefix="/api/v1")
    app.include_router(media_router, prefix="/api/v1")
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, engine, tmp_path
    engine.dispose()


def auth_headers(user_id=1):
    token = jwt.encode(
        {"sub": str(user_id)}, get_settings().jwt_secret_key, algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}


def upload(client, content=None, slot="landing-light"):
    return client.put(
        LOGO_URL,
        files={
            "file": (
                "logo.png",
                image_bytes() if content is None else content,
                "image/png",
            )
        },
        params={"slot": slot},
        headers=auth_headers(),
    )


def saved_files(storage):
    return {
        path.relative_to(storage): path.read_bytes() for path in storage.rglob("*.png")
    }


def test_public_configuration_has_no_logo_initially(logo_api):
    client, _, _ = logo_api
    response = client.get(CONFIG_URL)
    assert response.status_code == 200
    assert response.json()["data"]["logo_url"] is None
    data = response.json()["data"]
    for field in (
        "logo_dark_url",
        "system_logo_url",
        "system_logo_dark_url",
        "favicon_url",
    ):
        assert data[field] is None
    for field in (
        "logo_same_for_themes",
        "system_logo_same_for_themes",
        "system_uses_landing_logo",
    ):
        assert data[field] is True
    assert "logo_remove_background" not in data
    assert "logo_background_tolerance" not in data
    assert "logo_original_url" not in response.json()["data"]


@pytest.mark.parametrize(("user_id", "status"), [(None, 401), (2, 403), (3, 401)])
def test_only_active_administrators_can_change_logo(logo_api, user_id, status):
    client, engine, storage = logo_api
    response = client.put(
        LOGO_URL,
        files={"file": ("logo.png", image_bytes(), "image/png")},
        headers=auth_headers(user_id) if user_id else {},
    )
    assert response.status_code == status
    with Session(engine) as session:
        assert session.get(OfficeConfig, 1).logo_url is None
    assert not list(storage.rglob("*.png"))


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_supported_formats_are_persisted_and_publicly_served_as_png(logo_api, format):
    client, engine, _ = logo_api
    # Content decoding, rather than a user-controlled filename or MIME, decides format.
    response = client.put(
        LOGO_URL,
        files={"file": ("logo.bin", image_bytes(format), "application/octet-stream")},
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    url = response.json()["data"]["logo_url"]
    assert "/api/v1/media/logos/" in url
    assert url.endswith(".png")
    with Session(engine) as session:
        assert session.get(OfficeConfig, 1).logo_url == url
    assert client.get(CONFIG_URL).json()["data"]["logo_url"] == url
    media = client.get(url)
    assert media.status_code == 200
    assert media.headers["content-type"] == "image/png"
    with Image.open(BytesIO(media.content)) as saved:
        assert saved.format == "PNG"
        assert saved.size == (80, 40)  # Small originals must not be upscaled.


def test_replacement_has_new_url_preserves_aspect_alpha_and_other_settings(logo_api):
    client, engine, _ = logo_api
    client.patch(CONFIG_URL, json={"office_name": "My Office"}, headers=auth_headers())
    first_url = upload(client).json()["data"]["logo_url"]
    response = upload(client, image_bytes(size=(1600, 800)))
    assert response.status_code == 200, response.text
    new_url = response.json()["data"]["logo_url"]
    assert new_url != first_url
    with Session(engine) as session:
        config = session.get(OfficeConfig, 1)
        assert config.logo_url == new_url
        assert config.office_name == "My Office"
    # A fresh HTTP client and DB session must see the saved configuration.
    with TestClient(client.app) as reloaded_client:
        assert reloaded_client.get(CONFIG_URL).json()["data"]["logo_url"] == new_url
        media = reloaded_client.get(new_url)
    assert media.status_code == 200
    with Image.open(BytesIO(media.content)) as saved:
        assert saved.size == (1024, 512)
        assert saved.mode == "RGBA"
        assert saved.getpixel((512, 256))[3] == 128


def test_logo_and_color_updates_preserve_each_other(logo_api):
    client, engine, _ = logo_api
    colors = {
        "color": "#123456",
        "color_bg_primary": "#102030",
        "color_buttons": "#abcdef",
    }
    response = client.patch(CONFIG_URL, json=colors, headers=auth_headers())
    assert response.status_code == 200, response.text

    for size in [(80, 40), (160, 80)]:
        response = upload(client, image_bytes(size=size))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        for field, value in colors.items():
            assert data[field] == value
    logo_url = data["logo_url"]

    colors["color_buttons"] = "#fedcba"
    response = client.patch(
        CONFIG_URL,
        json={"color_buttons": colors["color_buttons"]},
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["logo_url"] == logo_url
    with Session(engine) as session:
        config = session.get(OfficeConfig, 1)
        assert config.logo_url == logo_url
        for field, value in colors.items():
            assert getattr(config, field) == value
    public_config = client.get(CONFIG_URL).json()["data"]
    assert public_config["logo_url"] == logo_url
    for field, value in colors.items():
        assert public_config[field] == value
    assert client.get(logo_url).status_code == 200


@pytest.mark.parametrize(
    ("content", "status", "code"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", 422, "INVALID_LOGO_IMAGE"),
        (b"not an image", 415, "INVALID_MIME_TYPE"),
        (b"", 415, "INVALID_MIME_TYPE"),
        (b"x" * (5 * 1024 * 1024 + 1), 413, "FILE_TOO_LARGE"),
    ],
    ids=[
        "invalid-svg-disguised-as-png",
        "invalid-content",
        "empty-file",
        "over-five-mib",
    ],
)
def test_invalid_replacement_preserves_previous_logo(logo_api, content, status, code):
    client, engine, storage = logo_api
    first_url = upload(client).json()["data"]["logo_url"]
    original_bytes = client.get(first_url).content
    existing_files = set(storage.rglob("*.png"))
    response = upload(client, content)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    with Session(engine) as session:
        assert session.get(OfficeConfig, 1).logo_url == first_url
    assert client.get(CONFIG_URL).json()["data"]["logo_url"] == first_url
    assert client.get(first_url).content == original_bytes
    assert set(storage.rglob("*.png")) == existing_files


@pytest.mark.parametrize(
    "payload",
    [
        {"logo_url": "https://example.test/unvalidated.svg"},
        {"logo_original_url": "https://example.test/unvalidated.svg"},
        {"logo_dark_url": "https://example.test/unvalidated.svg"},
        {"system_logo_url": "https://example.test/unvalidated.svg"},
        {"system_logo_dark_url": "https://example.test/unvalidated.svg"},
        {"favicon_url": "https://example.test/unvalidated.svg"},
        {"default_logo_url": "https://example.test/unvalidated.svg"},
        {"system_uses_landing_logo": False},
        {"logo_remove_background": True},
        {"logo_background_tolerance": 100},
    ],
)
def test_generic_patch_cannot_bypass_logo_validation(logo_api, payload):
    client, engine, _ = logo_api
    first_url = upload(client).json()["data"]["logo_url"]
    response = client.patch(
        CONFIG_URL,
        json=payload,
        headers=auth_headers(),
    )
    assert response.status_code == 422
    with Session(engine) as session:
        assert session.get(OfficeConfig, 1).logo_url == first_url
    assert client.get(first_url).status_code == 200


@pytest.mark.parametrize(("method", "url"), [("put", LOGO_URL), ("post", PREVIEW_URL)])
def test_missing_file_is_rejected_without_changing_configuration(logo_api, method, url):
    client, engine, _ = logo_api
    response = client.request(method, url, headers=auth_headers())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    with Session(engine) as session:
        assert session.get(OfficeConfig, 1).logo_url is None


SLOTS = {
    "landing-light": "logo_url",
    "landing-dark": "logo_dark_url",
    "system-light": "system_logo_url",
    "system-dark": "system_logo_dark_url",
    "favicon": "favicon_url",
}


@pytest.mark.parametrize(("user_id", "status"), [(None, 401), (2, 403), (3, 401)])
@pytest.mark.parametrize("method", ["delete", "post", "put", "patch"])
@pytest.mark.parametrize("slot", SLOTS)
def test_all_branding_mutations_require_active_admin(
    logo_api, user_id, status, method, slot
):
    client, _, storage = logo_api
    upload(client)
    previous = client.get(CONFIG_URL).json()["data"]
    files = saved_files(storage)
    kwargs = {}
    if method in {"post", "put"}:
        kwargs["files"] = {"file": ("logo.png", image_bytes(), "image/png")}
    if method == "patch":
        kwargs["json"] = {"system_uses_landing_logo": False}
    response = client.request(
        method,
        PREVIEW_URL if method == "post" else LOGO_URL,
        params={"slot": slot},
        headers=auth_headers(user_id) if user_id else {},
        **kwargs,
    )
    assert response.status_code == status
    assert client.get(CONFIG_URL).json()["data"] == previous
    assert saved_files(storage) == files


@pytest.mark.parametrize("slot,field", SLOTS.items())
def test_preview_is_ephemeral_and_matches_saved_image(logo_api, slot, field):
    client, _, storage = logo_api
    previous = client.get(CONFIG_URL).json()["data"]
    files = saved_files(storage)
    content = image_bytes(size=(800, 400), color="white")
    response = client.post(
        PREVIEW_URL,
        params={"slot": slot},
        files={"file": ("logo.png", content, "image/png")},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert client.get(CONFIG_URL).json()["data"] == previous
    assert saved_files(storage) == files
    data = upload(client, content, slot).json()["data"]
    assert client.get(data[field]).content == response.content
    with Image.open(BytesIO(response.content)) as image:
        assert image.getpixel((image.width // 2, image.height // 2)) == (
            255,
            255,
            255,
            255,
        )
        if slot == "favicon":
            assert image.size == (256, 256)
            assert image.getchannel("A").getbbox() == (0, 64, 256, 192)
        else:
            assert image.size == (800, 400)
            assert image.getchannel("A").getextrema() == (255, 255)


def test_variants_modes_and_individual_resets_are_independent_and_persistent(logo_api):
    client, _, storage = logo_api
    settings = {"office_name": "Office", "color": "#123456"}
    client.patch(CONFIG_URL, json=settings, headers=auth_headers())
    urls = {}
    for slot, field in SLOTS.items():
        response = upload(client, slot=slot)
        assert response.status_code == 200
        urls[field] = response.json()["data"][field]
    assert len(set(urls.values())) == 5
    files = saved_files(storage)
    modes = {
        "logo_same_for_themes": False,
        "system_uses_landing_logo": False,
        "system_logo_same_for_themes": False,
    }
    for shared in [False, True, False]:
        modes = dict.fromkeys(modes, shared)
        response = client.patch(LOGO_URL, json=modes, headers=auth_headers())
        assert response.status_code == 200
        data = response.json()["data"]
        for field, value in {**urls, **modes, **settings}.items():
            assert data[field] == value
        assert saved_files(storage) == files
    with TestClient(client.app) as reloaded:
        assert reloaded.get(CONFIG_URL).json()["data"] == data
    # Restoring each version must leave other versions and sharing choices untouched.
    for slot, field in SLOTS.items():
        old_url = urls[field]
        for _ in range(2):
            response = client.delete(
                LOGO_URL, params={"slot": slot}, headers=auth_headers()
            )
            assert response.status_code == 200
            urls[field] = None
            for key, value in {**urls, **modes, **settings}.items():
                assert response.json()["data"][key] == value
        assert client.get(old_url).status_code == 404
    assert not saved_files(storage)


@pytest.mark.parametrize(
    "payload",
    [
        {"system_uses_landing_logo": None},
        {"logo_same_for_themes": "false"},
        {"system_logo_same_for_themes": 1},
        {"favicon_url": "https://evil.test/x.svg"},
        {"logo_remove_background": True},
        {"logo_background_tolerance": 50},
    ],
)
def test_invalid_branding_preferences_are_rejected(logo_api, payload):
    client, _, _ = logo_api
    previous = client.get(CONFIG_URL).json()["data"]
    response = client.patch(LOGO_URL, json=payload, headers=auth_headers())
    assert response.status_code == 422
    assert client.get(CONFIG_URL).json()["data"] == previous


@pytest.mark.parametrize("method", ["put", "post", "delete"])
def test_invalid_slot_cannot_write_arbitrary_fields(logo_api, method):
    client, _, storage = logo_api
    response = client.request(
        method,
        PREVIEW_URL if method == "post" else LOGO_URL,
        params={"slot": "office_name"},
        headers=auth_headers(),
        files={"file": ("logo.png", image_bytes(), "image/png")}
        if method != "delete"
        else None,
    )
    assert response.status_code == 422
    assert not saved_files(storage)


@pytest.mark.parametrize("slot", SLOTS)
@pytest.mark.parametrize("method", ["put", "post"])
@pytest.mark.parametrize(
    "content,status",
    [(b"<svg/>", 422), (b"", 415), (b"x" * (5 * 1024 * 1024 + 1), 413)],
)
def test_every_variant_validates_content_and_keeps_previous_on_failure(
    logo_api, slot, method, content, status
):
    client, _, storage = logo_api
    upload(client, slot=slot)
    previous = client.get(CONFIG_URL).json()["data"]
    files = saved_files(storage)
    response = client.request(
        method,
        PREVIEW_URL if method == "post" else LOGO_URL,
        params={"slot": slot},
        files={"file": ("invalid.png", content, "image/png")},
        headers=auth_headers(),
    )
    assert response.status_code == status
    assert client.get(CONFIG_URL).json()["data"] == previous
    assert saved_files(storage) == files


@pytest.mark.parametrize("slot", SLOTS)
@pytest.mark.parametrize("method", ["put", "delete", "patch"])
def test_failed_commit_preserves_images_and_preferences(
    logo_api, monkeypatch, slot, method
):
    client, _, storage = logo_api
    upload(client, slot=slot)
    previous = client.get(CONFIG_URL).json()["data"]
    files = saved_files(storage)

    def fail_commit(*args):
        raise RuntimeError("simulated commit failure")

    kwargs = {"json": {"system_uses_landing_logo": False}} if method == "patch" else {}
    if method == "put":
        kwargs["files"] = {"file": ("logo.png", image_bytes(), "image/png")}
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            client.request(
                method,
                LOGO_URL,
                params={"slot": slot},
                headers=auth_headers(),
                **kwargs,
            )
    assert client.get(CONFIG_URL).json()["data"] == previous
    assert saved_files(storage) == files


def test_reset_does_not_remove_asset_used_by_another_variant(logo_api):
    client, engine, _ = logo_api
    url = upload(client).json()["data"]["logo_url"]
    with Session(engine) as session:
        session.get(OfficeConfig, 1).system_logo_url = url
        session.commit()
    response = client.delete(LOGO_URL, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["data"]["logo_url"] is None
    assert response.json()["data"]["system_logo_url"] == url
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("slot,field", SLOTS.items())
def test_svg_default_survives_replacement_and_can_be_restored_or_cleared(
    logo_api, slot, field
):
    client, _, storage = logo_api
    content = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40"><rect width="80" height="40" fill="red"/></svg>'
    response = client.put(
        LOGO_URL,
        params={"slot": slot},
        data={"make_default": "true"},
        files={"file": ("logo.svg", content, "image/svg+xml")},
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    default_url = data[field]
    assert data[f"default_{field}"] == default_url
    assert client.get(default_url).headers["content-type"] == "image/png"
    replacement_url = upload(client, slot=slot).json()["data"][field]
    assert replacement_url != default_url
    assert client.get(default_url).status_code == 200
    with TestClient(client.app) as reloaded:
        assert (
            reloaded.get(CONFIG_URL).json()["data"][f"default_{field}"] == default_url
        )
    restored = client.delete(
        LOGO_URL, params={"slot": slot}, headers=auth_headers()
    ).json()["data"]
    assert restored[field] == default_url
    assert restored[f"default_{field}"] == default_url
    assert client.get(replacement_url).status_code == 404
    cleared = client.delete(
        LOGO_URL, params={"slot": slot, "factory": "true"}, headers=auth_headers()
    ).json()["data"]
    assert cleared[field] is None and cleared[f"default_{field}"] is None
    assert client.get(default_url).status_code == 404
    assert not saved_files(storage)


@pytest.mark.parametrize("slot,field", SLOTS.items())
def test_current_logo_can_be_promoted_without_upload_and_old_default_is_cleaned(
    logo_api, slot, field
):
    client, _, _ = logo_api
    assert (
        client.post(
            f"{LOGO_URL}/default", params={"slot": slot}, headers=auth_headers()
        ).status_code
        == 422
    )
    first = upload(client, slot=slot).json()["data"][field]
    response = client.post(
        f"{LOGO_URL}/default", params={"slot": slot}, headers=auth_headers()
    )
    assert response.status_code == 200
    assert response.json()["data"][f"default_{field}"] == first
    second = upload(client, slot=slot).json()["data"][field]
    response = client.post(
        f"{LOGO_URL}/default", params={"slot": slot}, headers=auth_headers()
    )
    assert response.json()["data"][field] == second
    assert response.json()["data"][f"default_{field}"] == second
    assert client.get(first).status_code == 404
    assert client.get(second).status_code == 200


@pytest.mark.parametrize("user,status", [(None, 401), (2, 403), (3, 401)])
def test_default_changes_require_active_admin(logo_api, user, status):
    client, _, storage = logo_api
    upload(client)
    previous = client.get(CONFIG_URL).json()["data"]
    files = saved_files(storage)
    for method, url, options in [
        ("post", f"{LOGO_URL}/default", {}),
        ("delete", LOGO_URL, {"params": {"factory": "true"}}),
        (
            "put",
            LOGO_URL,
            {
                "data": {"make_default": "true"},
                "files": {"file": ("logo.png", image_bytes(), "image/png")},
            },
        ),
    ]:
        response = client.request(
            method, url, headers=auth_headers(user) if user else {}, **options
        )
        assert response.status_code == status
    assert client.get(CONFIG_URL).json()["data"] == previous
    assert saved_files(storage) == files


@pytest.mark.parametrize("operation", ["upload", "promote", "factory"])
def test_failed_default_commit_preserves_previous_assets(
    logo_api, monkeypatch, operation
):
    client, _, storage = logo_api
    upload(client)
    client.post(f"{LOGO_URL}/default", headers=auth_headers())
    upload(client)
    previous = client.get(CONFIG_URL).json()["data"]
    files = saved_files(storage)

    def fail_commit(*args):
        raise RuntimeError("default commit failed")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="default commit failed"):
            if operation == "upload":
                client.put(
                    LOGO_URL,
                    data={"make_default": "true"},
                    files={"file": ("logo.png", image_bytes(), "image/png")},
                    headers=auth_headers(),
                )
            elif operation == "promote":
                client.post(f"{LOGO_URL}/default", headers=auth_headers())
            else:
                client.delete(
                    LOGO_URL, params={"factory": "true"}, headers=auth_headers()
                )
    assert client.get(CONFIG_URL).json()["data"] == previous
    assert saved_files(storage) == files
