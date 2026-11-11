import os
import re

import httpx
import pytest

from app.modules.email.errors import EmailSendError
from app.modules.email.fake_service import FakeEmailService
from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus

USERS_URL = "/api/v1/users"
INVITES_URL = "/api/v1/invites"
PASSWORD = "NovaSenha@123"


def _token(message) -> str:
    return re.search(r"/convite/([A-Za-z0-9_-]+)", message.text).group(1)


@pytest.fixture
def invited(client, admin_headers, created_user_ids, fake_email, drain_outbox):
    response = client.post(
        USERS_URL,
        json={"name": "Convidada", "email": "e2e_invited@test.com"},
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    user = response.json()["data"]
    created_user_ids.append(user["id"])
    drain_outbox()
    return user, _token(fake_email.messages[-1])


class TestCreateWithInvite:
    def test_user_is_invited_with_pending_invite(self, invited):
        user, _ = invited

        assert user["status"] == "INVITED"
        assert user["invite"]["status"] == "PENDING"

    def test_invite_email_has_no_password(self, invited, fake_email):
        message = fake_email.messages[-1]

        assert "/convite/" in message.html
        assert "senha temporária" not in message.html.lower()

    def test_smtp_down_returns_201_and_email_waits_in_queue(
        self, client, admin_headers, created_user_ids, db_session, run_outbox
    ):
        response = client.post(
            USERS_URL,
            json={"name": "Sem SMTP", "email": "e2e_nosmtp@test.com"},
            headers=admin_headers,
        )
        user_id = response.json()["data"]["id"]
        created_user_ids.append(user_id)
        failing = FakeEmailService(
            fail_with=EmailSendError(
                "down", transient=True, failover=True, provider="smtp"
            )
        )
        run_outbox(failing)

        assert response.status_code == 201
        # O convite existe: o admin vê pendente e pode reenviar.
        assert response.json()["data"]["invite"]["status"] == "PENDING"
        item = (
            db_session.query(EmailOutboxItem)
            .filter_by(related_type="user", related_id=user_id)
            .one()
        )
        assert item.status == EmailStatus.FAILED
        assert item.next_attempt_at is not None

    def test_last_sent_comes_from_email_history(self, client, admin_headers, invited):
        user, _ = invited

        data = client.get(f"{USERS_URL}/{user['id']}", headers=admin_headers).json()

        assert data["data"]["invite"]["email_status"] == "SENT"
        assert data["data"]["invite"]["last_sent_at"] is not None

    def test_login_before_accepting_is_refused(self, client, invited):
        user, _ = invited

        response = client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": "qualquer"}
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "INVITE_NOT_ACCEPTED"


class TestPublicFlow:
    def test_get_returns_name_and_email(self, client, invited):
        user, token = invited

        response = client.get(f"{INVITES_URL}/{token}")

        assert response.status_code == 200
        assert response.json()["data"] == {"name": user["name"], "email": user["email"]}

    def test_unknown_token_returns_404(self, client):
        response = client.get(f"{INVITES_URL}/nao-existe")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "INVITE_INVALID"

    def test_accept_returns_jwt_and_allows_login(self, client, invited):
        user, token = invited

        accepted = client.post(
            f"{INVITES_URL}/{token}/accept", json={"password": PASSWORD}
        )
        login = client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD}
        )

        assert accepted.status_code == 200
        assert accepted.json()["data"]["access_token"]
        assert login.status_code == 200

    def test_accept_twice_fails(self, client, invited):
        _, token = invited
        client.post(f"{INVITES_URL}/{token}/accept", json={"password": PASSWORD})

        again = client.post(
            f"{INVITES_URL}/{token}/accept", json={"password": PASSWORD}
        )

        assert again.status_code == 410
        assert again.json()["error"]["code"] == "INVITE_ALREADY_USED"

    def test_short_password_is_rejected(self, client, invited):
        _, token = invited

        response = client.post(
            f"{INVITES_URL}/{token}/accept", json={"password": "123"}
        )

        assert response.status_code == 422


class TestAdminActions:
    def test_resend_invalidates_previous_link(
        self, client, admin_headers, invited, fake_email, drain_outbox
    ):
        user, old_token = invited

        response = client.post(
            f"{USERS_URL}/{user['id']}/invite/resend", headers=admin_headers
        )
        drain_outbox()
        new_token = _token(fake_email.messages[-1])

        assert response.status_code == 200
        assert new_token != old_token
        assert client.get(f"{INVITES_URL}/{old_token}").status_code == 404
        assert client.get(f"{INVITES_URL}/{new_token}").status_code == 200

    def test_cancel(self, client, admin_headers, invited):
        user, token = invited

        response = client.delete(
            f"{USERS_URL}/{user['id']}/invite", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["data"]["invite"]["status"] == "CANCELLED"
        assert client.get(f"{INVITES_URL}/{token}").status_code == 404

    def test_user_cannot_resend(self, client, user_headers, invited):
        user, _ = invited

        response = client.post(
            f"{USERS_URL}/{user['id']}/invite/resend", headers=user_headers
        )

        assert response.status_code == 403


MAILPIT_API = f"http://{os.getenv('MAILPIT_HOST', 'localhost')}:8025/api/v1"


@pytest.mark.mailpit
def test_full_flow_through_mailpit(client, admin_headers, created_user_ids, run_outbox):
    """Criar -> abrir o link no Mailpit -> definir senha -> entrar."""
    from app.modules.email.failover import FailoverEmailService
    from app.modules.email.smtp_provider import SmtpConfig, SmtpProvider

    mailpit = httpx.Client(base_url=MAILPIT_API, timeout=5)
    try:
        mailpit.get("/messages", params={"limit": 1}).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Mailpit não está rodando em localhost:8025")

    smtp = FailoverEmailService(
        [
            SmtpProvider(
                SmtpConfig(
                    host=os.getenv("MAILPIT_HOST", "localhost"),
                    port=1025,
                    security="none",
                    from_email="noreply@advocacia.local",
                )
            )
        ]
    )
    email = "e2e_mailpit_invite@test.com"
    created = client.post(
        USERS_URL,
        json={"name": "Via Mailpit", "email": email},
        headers=admin_headers,
    )
    created_user_ids.append(created.json()["data"]["id"])
    run_outbox(smtp)

    found = mailpit.get("/search", params={"query": f"to:{email}"}).json()
    assert found["messages"], "convite não chegou ao Mailpit"
    message = mailpit.get(f"/message/{found['messages'][0]['ID']}").json()
    token = re.search(r"/convite/([A-Za-z0-9_-]+)", message["Text"]).group(1)

    assert (
        client.post(
            f"{INVITES_URL}/{token}/accept", json={"password": PASSWORD}
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200
