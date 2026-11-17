from types import SimpleNamespace
from unittest.mock import MagicMock

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
from app.modules.email_settings.deps import get_gmail_connect_service
from app.modules.email_settings.gmail import GmailConnectError
from app.modules.email_settings.router import router
from app.modules.users.model import User
from app.shared.db.base_model import Base
from app.shared.exceptions import AppException, GmailNotConfiguredError
from app.shared.types import Role

URL = "/api/v1/email-settings/gmail"


def headers(user_id: int) -> dict:
    token = jwt.encode(
        {"sub": str(user_id)}, get_settings().jwt_secret_key, algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def gmail():
    return MagicMock()


@pytest.fixture
def client(gmail):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for user_id, role in [(1, Role.ADMIN), (2, Role.USER)]:
            db.add(
                User(
                    id=user_id,
                    name=f"User {user_id}",
                    email=f"gmail-{user_id}@example.test",
                    hashed_password="unused",
                    role=role,
                    is_active=True,
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
    app.dependency_overrides[get_gmail_connect_service] = lambda: gmail
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
    engine.dispose()


def test_admin_gets_the_consent_url(client, gmail):
    gmail.build_auth_url.return_value = "https://accounts.google.com/o/oauth2/auth?x=1"

    response = client.get(f"{URL}/auth-url", headers=headers(1))

    assert response.status_code == 200
    assert response.json()["data"]["auth_url"].startswith("https://accounts.google.com")
    gmail.build_auth_url.assert_called_once_with(1)


def test_consent_url_is_admin_only(client, gmail):
    assert client.get(f"{URL}/auth-url", headers=headers(2)).status_code == 403
    assert client.get(f"{URL}/auth-url").status_code == 401
    gmail.build_auth_url.assert_not_called()


def test_server_without_google_credentials_answers_503(client, gmail):
    gmail.build_auth_url.side_effect = GmailNotConfiguredError()

    response = client.get(f"{URL}/auth-url", headers=headers(1))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GMAIL_NOT_CONFIGURED"


@pytest.mark.parametrize(
    ("query", "effect", "result"),
    [
        ("code=c&state=s", None, "connected"),
        ("code=c&state=s", GmailConnectError("permission", "x"), "permission"),
        ("code=c&state=s", RuntimeError("boom"), "error"),
        ("error=access_denied", None, "cancelled"),
        ("", None, "error"),
    ],
)
def test_callback_returns_to_the_settings_page(client, gmail, query, effect, result):
    gmail.handle_callback.side_effect = effect

    response = client.get(f"{URL}/callback?{query}")

    assert response.status_code == 302
    assert response.headers["location"].endswith(
        f"/sistema/configuracoes-email?gmail={result}"
    )


def test_disconnect_is_admin_only(client, gmail):
    assert client.delete(URL, headers=headers(2)).status_code == 403
    gmail.disconnect.assert_not_called()

    response = client.delete(URL, headers=headers(1))

    assert response.status_code == 204
    gmail.disconnect.assert_called_once()


def test_overview_tells_the_page_if_gmail_is_available(client, gmail):
    from app.modules.email_settings.deps import get_email_settings_service

    service = MagicMock()
    service.list_profiles.return_value = []
    service.get_identity.return_value = SimpleNamespace(
        from_name=None, reply_to=None, version=1, updated_at=None
    )
    service.system_account_email.return_value = None
    client.app.dependency_overrides[get_email_settings_service] = lambda: service
    gmail.available = True

    response = client.get("/api/v1/email-settings", headers=headers(1))

    assert response.status_code == 200
    assert response.json()["data"]["gmail_available"] is True
