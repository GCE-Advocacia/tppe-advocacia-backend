import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String, cast, create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.main import app
from app.modules.email.fake_service import FakeEmailService
from app.modules.email_outbox.model import EmailOutboxItem
from app.modules.google_calendar.fake_service import FakeGoogleCalendarClient
from app.modules.tasks.model import Task
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.deps.email import get_email_service
from app.shared.deps.google import get_google_calendar_client
from app.shared.types import Role

app.dependency_overrides[get_email_service] = lambda: FakeEmailService()
app.dependency_overrides[get_google_calendar_client] = (
    lambda: FakeGoogleCalendarClient()
)


@pytest.fixture(scope="session", autouse=True)
def require_database():
    settings = get_settings()
    try:
        engine = create_engine(
            settings.database_url,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception:
        pytest.skip("PostgreSQL unavailable — run: docker-compose up -d db")


@pytest.fixture(scope="session", autouse=True)
def run_migrations(require_database):
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
def db_engine():
    from app.db.database import engine

    return engine


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _teardown_user(db_session: Session, user_id: int) -> None:
    db_session.rollback()
    email = db_session.scalar(select(User.email).where(User.id == user_id))
    if email:
        # E-mails que o teste deixou na fila para este usuário.
        db_session.execute(
            delete(EmailOutboxItem).where(
                cast(EmailOutboxItem.to, String).ilike(f"%{email}%")
            )
        )
    db_session.execute(
        delete(Task).where(
            (Task.created_by == user_id)
            | (Task.updated_by == user_id)
            | (Task.assigned_to == user_id)
        )
    )
    db_session.execute(delete(User).where(User.id == user_id))
    db_session.commit()


@pytest.fixture
def active_user(db_session):
    password = "Valid@1234"
    user = UserRepository(db_session).create(
        name="Active User",
        email="e2e_active@test.com",
        hashed_password=_hash(password),
        role=Role.USER,
    )
    db_session.commit()
    yield {"id": user.id, "email": user.email, "password": password}
    _teardown_user(db_session, user.id)


@pytest.fixture
def inactive_user(db_session):
    password = "Valid@1234"
    repo = UserRepository(db_session)
    user = repo.create(
        name="Inactive User",
        email="e2e_inactive@test.com",
        hashed_password=_hash(password),
        role=Role.USER,
    )
    repo.update(user, {"is_active": False})
    db_session.commit()
    yield {"id": user.id, "email": user.email, "password": password}
    _teardown_user(db_session, user.id)


@pytest.fixture
def admin_user(db_session):
    password = "Valid@1234"
    user = UserRepository(db_session).create(
        name="Admin User",
        email="e2e_admin@test.com",
        hashed_password=_hash(password),
        role=Role.ADMIN,
    )
    db_session.commit()
    yield {"id": user.id, "email": user.email, "password": password}
    _teardown_user(db_session, user.id)


@pytest.fixture
def admin_headers(client, admin_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers(client, active_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": active_user["email"], "password": active_user["password"]},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def created_user_ids(db_session):
    ids = []
    yield ids
    for uid in ids:
        db_session.execute(
            delete(EmailOutboxItem).where(
                EmailOutboxItem.related_type == "user",
                EmailOutboxItem.related_id == uid,
            )
        )
        db_session.execute(delete(User).where(User.id == uid))
    db_session.commit()


@pytest.fixture
def fake_email():
    svc = FakeEmailService()
    app.dependency_overrides[get_email_service] = lambda: svc
    yield svc
    app.dependency_overrides[get_email_service] = lambda: FakeEmailService()


def _run_outbox(provider) -> int:
    """Roda o worker da fila uma vez com ``provider``, como o scheduler faria."""
    from app.db.database import SessionLocal
    from app.modules.email_outbox.repository import EmailOutboxRepository
    from app.modules.email_outbox.service import EmailOutboxWorker
    from app.shared.deps.email import get_email_renderer

    with SessionLocal() as db:
        worker = EmailOutboxWorker(
            EmailOutboxRepository(db), get_email_renderer(), provider, get_settings()
        )
        return worker.run_once()


@pytest.fixture
def run_outbox():
    return _run_outbox


class QueuedFake:
    """Os envios agora passam pela fila: ler ``sent`` ou ``messages``
    processa a fila antes, como o scheduler faria."""

    def __init__(self, inner: FakeEmailService) -> None:
        self.inner = inner

    @property
    def sent(self) -> list[dict]:
        _run_outbox(self.inner)
        return self.inner.sent

    @property
    def messages(self) -> list:
        _run_outbox(self.inner)
        return self.inner.messages


@pytest.fixture
def queued_email(fake_email):
    # O que outros testes deixaram na fila sai antes, num fake descartado.
    _run_outbox(FakeEmailService())
    return QueuedFake(fake_email)


@pytest.fixture
def drain_outbox(fake_email):
    return lambda: _run_outbox(fake_email)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
