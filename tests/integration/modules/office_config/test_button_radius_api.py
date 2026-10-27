import jwt
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings
from app.db.database import get_db
from app.main import app_exception_handler, validation_exception_handler
from app.modules.office_config.model import OfficeConfig
from app.modules.office_config.router import router
from app.modules.users.model import User
from app.shared.exceptions import AppException
from app.shared.types import Role

URL = "/api/v1/office-config"


def headers(user_id=1):
    token = jwt.encode(
        {"sub": str(user_id)}, get_settings().jwt_secret_key, algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def radius_api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    OfficeConfig.__table__.create(engine)
    User.__table__.create(engine)
    with Session(engine) as db:
        db.add(OfficeConfig(id=1, color="#123456", logo_url="logo.png"))
        for user_id, role, active in [
            (1, Role.ADMIN, True),
            (2, Role.USER, True),
            (3, Role.ADMIN, False),
        ]:
            db.add(
                User(
                    id=user_id,
                    name=f"User {user_id}",
                    email=f"radius-{user_id}@example.test",
                    hashed_password="unused",
                    role=role,
                    is_active=active,
                )
            )
        db.commit()

    def database():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.dependency_overrides[get_db] = database
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, engine
    engine.dispose()


def test_public_config_exposes_default_radius(radius_api):
    client, _ = radius_api
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["data"]["button_radius"] == "6px"


@pytest.mark.parametrize("value", ["0px", "6px", "12px", "999px", "17px", "24px"])
def test_admin_saves_radius_and_new_session_reads_it(radius_api, value):
    client, engine = radius_api
    response = client.patch(URL, json={"button_radius": value}, headers=headers())
    assert response.status_code == 200
    assert response.json()["data"]["button_radius"] == value
    with Session(engine) as db:
        config = db.get(OfficeConfig, 1)
        assert config.button_radius == value
        assert config.color == "#123456"
        assert config.logo_url == "logo.png"
    assert client.get(URL).json()["data"]["button_radius"] == value
    response = client.patch(URL, json={"office_name": "Novo nome"}, headers=headers())
    assert response.status_code == 200
    assert response.json()["data"]["button_radius"] == value


@pytest.mark.parametrize(("user_id", "status"), [(None, 401), (2, 403), (3, 401)])
def test_only_active_administrators_can_change_radius(radius_api, user_id, status):
    client, engine = radius_api
    response = client.patch(
        URL, json={"button_radius": "12px"}, headers=headers(user_id) if user_id else {}
    )
    assert response.status_code == status
    with Session(engine) as db:
        assert db.get(OfficeConfig, 1).button_radius == "6px"


@pytest.mark.parametrize(
    "value", [None, 12, "-1px", "25px", "6em", "9999px", "6px; background:red"]
)
def test_invalid_radius_returns_422_without_changing_saved_config(radius_api, value):
    client, _ = radius_api
    response = client.patch(URL, json={"button_radius": value}, headers=headers())
    assert response.status_code == 422
    assert client.get(URL).json()["data"]["button_radius"] == "6px"


def test_failed_commit_keeps_previous_radius(radius_api, monkeypatch):
    client, engine = radius_api

    def fail_commit(self):
        raise RuntimeError("Database unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        response = client.patch(URL, json={"button_radius": "24px"}, headers=headers())
    assert response.status_code == 500
    with Session(engine) as db:
        assert db.get(OfficeConfig, 1).button_radius == "6px"
