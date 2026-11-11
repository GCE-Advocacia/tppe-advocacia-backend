"""US25: e-mail do escritório sem campos técnicos."""

import os
import socket

import httpx
import pytest
from sqlalchemy import delete, update

from app.main import app
from app.modules.audit_logs.model import AuditAction, AuditLog
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.modules.email_settings.model import EmailIdentity, EmailProfile
from app.shared.deps.email import get_email_service

BASE = "/api/v1/email-settings"
MAILPIT_HOST = os.getenv("MAILPIT_HOST", "localhost")
MAILPIT_API = f"http://{MAILPIT_HOST}:8025/api/v1"


@pytest.fixture(autouse=True)
def reset(db_session):
    yield
    db_session.rollback()
    db_session.execute(
        update(EmailProfile).values(
            host=None, port=587, security="starttls", username=None,
            secret_encrypted=None, from_email=None, preset=None, is_active=False,
            last_tested_at=None, last_test_ok=None, version=1, updated_by=None,
        )
    )
    db_session.execute(
        update(EmailIdentity).values(
            from_name=None, reply_to=None, last_test_at=None, last_test_ok=None,
            last_test_error=None, version=1, updated_by=None,
        )
    )
    db_session.execute(
        delete(AuditLog).where(AuditLog.action == AuditAction.EMAIL_SETTINGS_UPDATED)
    )
    db_session.commit()


class NamedFake(FakeEmailService):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", ""),
        ("get", "/presets"),
        ("get", "/status"),
        ("put", "/identity"),
        ("post", "/test-send-me"),
        ("get", "/profiles"),
    ],
)
def test_user_gets_403_on_every_route(client, user_headers, method, path):
    response = getattr(client, method)(
        f"{BASE}{path}",
        headers=user_headers,
        **({"json": {"version": 1}} if method == "put" else {}),
    )

    assert response.status_code == 403


def test_overview_without_configuration(client, admin_headers):
    data = client.get(BASE, headers=admin_headers).json()["data"]

    assert data["identity"]["from_name"] is None
    assert data["own_account"]["is_active"] is False
    assert "resend" not in str(data).lower() or data["own_account"]["provider"] == "smtp"


def test_presets_hide_resend(client, admin_headers):
    presets = client.get(f"{BASE}/presets", headers=admin_headers).json()["data"]

    assert [p["id"] for p in presets] == ["gmail", "outlook", "hostinger", "locaweb", "other"]
    gmail = presets[0]
    assert (gmail["host"], gmail["port"], gmail["security"]) == ("smtp.gmail.com", 587, "starttls")


def test_identity_is_saved(client, admin_headers):
    response = client.put(
        f"{BASE}/identity",
        json={"from_name": "Souza & Lima", "reply_to": "contato@souzalima.adv.br", "version": 1},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2


def test_status_without_own_account(client, admin_headers):
    status = client.get(f"{BASE}/status", headers=admin_headers).json()["data"]

    assert status["account"] == "system"
    assert status["own_account_configured"] is False


def test_send_me_goes_only_to_logged_admin(client, admin_headers, admin_user):
    system = NamedFake("system")
    app.dependency_overrides[get_email_service] = lambda: FailoverEmailService([system])
    try:
        response = client.post(f"{BASE}/test-send-me", headers=admin_headers)
    finally:
        app.dependency_overrides[get_email_service] = lambda: FakeEmailService()

    assert response.status_code == 200, response.text
    assert response.json()["data"]["to"] == admin_user["email"]
    assert [m.to for m in system.messages] == [[admin_user["email"]]]


@pytest.mark.mailpit
def test_full_wizard_against_mailpit(client, admin_headers, admin_user):
    """Escolher "Outro" -> preencher -> testar -> ativar -> enviar teste para mim."""
    try:
        socket.create_connection((MAILPIT_HOST, 1025), timeout=2).close()
        httpx.get(f"{MAILPIT_API}/messages", timeout=3).raise_for_status()
    except (OSError, httpx.HTTPError):
        pytest.skip("Mailpit não está rodando")
    httpx.delete(f"{MAILPIT_API}/messages", timeout=3)

    own = client.get(BASE, headers=admin_headers).json()["data"]["own_account"]
    form = {
        "preset": "other",
        "host": MAILPIT_HOST,
        "port": 1025,
        "security": "none",
        "username": None,
        "secret": None,
        "from_email": "contato@escritorio-teste.com.br",
        "is_active": True,
    }

    tested = client.post(
        f"{BASE}/profiles/{own['id']}/test-connection", json=form, headers=admin_headers
    ).json()["data"]
    assert tested["ok"] is True, tested

    saved = client.put(
        f"{BASE}/profiles/{own['id']}",
        json={**form, "version": own["version"]},
        headers=admin_headers,
    )
    assert saved.status_code == 200, saved.text
    client.put(
        f"{BASE}/identity",
        json={"from_name": "Escritório Teste", "reply_to": "atendimento@escritorio-teste.com.br", "version": 1},
        headers=admin_headers,
    )

    # Sem override: usa a cadeia real, montada a partir do banco.
    app.dependency_overrides.pop(get_email_service, None)
    try:
        sent = client.post(f"{BASE}/test-send-me", headers=admin_headers)
    finally:
        app.dependency_overrides[get_email_service] = lambda: FakeEmailService()

    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["account"] == "own"
    found = httpx.get(
        f"{MAILPIT_API}/search", params={"query": f"to:{admin_user['email']}"}, timeout=3
    ).json()
    assert found["messages"], "teste não chegou ao Mailpit"
    message = httpx.get(f"{MAILPIT_API}/message/{found['messages'][0]['ID']}", timeout=3).json()
    assert message["From"]["Name"] == "Escritório Teste"
    assert message["From"]["Address"] == "contato@escritorio-teste.com.br"
    assert message["ReplyTo"][0]["Address"] == "atendimento@escritorio-teste.com.br"

    status = client.get(f"{BASE}/status", headers=admin_headers).json()["data"]
    assert status["account"] == "own"
    assert status["last_test_ok"] is True
