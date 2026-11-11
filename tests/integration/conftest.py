from types import SimpleNamespace

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.shared.db.base_model import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def drive_api(tmp_path, monkeypatch):
    """API completa sobre SQLite, com o Google Drive trocado por um fake.

    Usuários: 1 = admin, 2 = usuário comum. `headers(user_id)` gera o token.
    """
    from app.api.router import api_router
    from app.config.settings import get_settings
    from app.db.database import get_db
    from app.main import app_exception_handler, validation_exception_handler
    from app.modules.google_drive.deps import get_drive_client_factory
    from app.modules.google_drive.fake_client import FakeDriveClient
    from app.modules.users.model import User
    from app.shared.exceptions import AppException
    from app.shared.types import Role

    settings = get_settings()
    for name, value in {
        "google_client_id": "client-id",
        "google_client_secret": "client-secret",
        "google_token_encryption_key": Fernet.generate_key().decode(),
        "document_storage": "drive",
        "documents_upload_dir": str(tmp_path / "documents"),
        "frontend_url": "http://front.test",
    }.items():
        monkeypatch.setattr(settings, name, value)

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id=1,
                    name="Admin",
                    email="admin@example.test",
                    hashed_password="unused",
                    role=Role.ADMIN,
                    is_active=True,
                ),
                User(
                    id=2,
                    name="Usuário",
                    email="user@example.test",
                    hashed_password="unused",
                    role=Role.USER,
                    is_active=True,
                ),
            ]
        )
        session.commit()

    def database():
        with Session(engine) as session:
            yield session

    fake = FakeDriveClient()
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_drive_client_factory] = lambda: lambda token: fake

    def headers(user_id: int = 1) -> dict[str, str]:
        token = jwt.encode(
            {"sub": str(user_id)}, settings.jwt_secret_key, algorithm="HS256"
        )
        return {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            fake=fake,
            headers=headers,
            session=lambda: Session(engine),
        )
    engine.dispose()
