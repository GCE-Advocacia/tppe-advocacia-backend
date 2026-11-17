import base64
import email
import json

import httpx
import pytest

from app.modules.email.errors import EmailSendError
from app.modules.email.gmail_provider import GmailConfig, GmailProvider
from app.modules.email.protocol import EmailMessage

TOKEN_URI = "https://oauth2.googleapis.com/token"
SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def config(**overrides) -> GmailConfig:
    values = {
        "refresh_token": "refresh-1",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "from_email": "escritorio@gmail.com",
        "from_name": "Souza Advocacia",
        "reply_to": "contato@souza.adv.br",
    }
    values.update(overrides)
    return GmailConfig(**values)


def message(**overrides) -> EmailMessage:
    values = {
        "to": ["cliente@example.com"],
        "subject": "Lembrete",
        "html": "<p>Olá</p>",
        "text": "Olá",
    }
    values.update(overrides)
    return EmailMessage(**values)


class FakeGoogle:
    """Responde como o endpoint de token e o de envio do Gmail."""

    def __init__(
        self, send_status=200, send_body=None, token_status=200, token_body=None
    ):
        self.send_status = send_status
        self.send_body = send_body if send_body is not None else {"id": "msg-1"}
        self.token_status = token_status
        self.token_body = (
            token_body
            if token_body is not None
            else {"access_token": "access-1", "expires_in": 3600}
        )
        self.token_calls = 0
        self.sent: list[dict] = []
        self.auth_headers: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URI:
            self.token_calls += 1
            return httpx.Response(self.token_status, json=self.token_body)
        assert str(request.url) == SEND_URI
        self.auth_headers.append(request.headers["Authorization"])
        self.sent.append(json.loads(request.content))
        return httpx.Response(self.send_status, json=self.send_body)

    def provider(self, **overrides) -> GmailProvider:
        return GmailProvider(
            config(**overrides), transport=httpx.MockTransport(self.handler)
        )


def decode(raw: str) -> email.message.Message:
    return email.message_from_bytes(base64.urlsafe_b64decode(raw))


def test_sends_raw_message_with_sender_reply_to_and_bcc():
    google = FakeGoogle()

    result = google.provider().deliver(message(bcc=["copia@escritorio.com.br"]))

    assert result.provider == "gmail"
    assert result.message_id == "msg-1"
    assert google.auth_headers == ["Bearer access-1"]
    mime = decode(google.sent[0]["raw"])
    assert mime["From"] == "Souza Advocacia <escritorio@gmail.com>"
    assert mime["To"] == "cliente@example.com"
    assert mime["Reply-To"] == "contato@souza.adv.br"
    # O Gmail tira o Bcc antes de entregar, mas precisa dele para o envelope.
    assert mime["Bcc"] == "copia@escritorio.com.br"
    assert mime["Subject"] == "Lembrete"


def test_reuses_the_access_token_until_it_expires():
    google = FakeGoogle()
    provider = google.provider()

    provider.deliver(message())
    provider.deliver(message())

    assert google.token_calls == 1
    assert len(google.sent) == 2


def test_revoked_access_fails_over_without_retrying():
    google = FakeGoogle(token_status=400, token_body={"error": "invalid_grant"})

    with pytest.raises(EmailSendError) as error:
        google.provider().deliver(message())

    assert error.value.failover is True
    assert error.value.transient is False
    assert "revogado" in error.value.reason
    assert google.sent == []


def test_token_endpoint_outage_is_transient():
    google = FakeGoogle(token_status=503, token_body={"error": "backend_error"})

    with pytest.raises(EmailSendError) as error:
        google.provider().deliver(message())

    assert error.value.transient is True
    assert error.value.failover is True


@pytest.mark.parametrize("status", [429, 500, 503])
def test_rate_limit_and_server_errors_are_retried_elsewhere(status):
    google = FakeGoogle(send_status=status, send_body={"error": {"message": "busy"}})

    with pytest.raises(EmailSendError) as error:
        google.provider().deliver(message())

    assert error.value.transient is True
    assert error.value.failover is True


def test_daily_quota_403_is_transient():
    body = {
        "error": {
            "message": "Daily sending quota exceeded",
            "errors": [{"reason": "userRateLimitExceeded"}],
        }
    }
    google = FakeGoogle(send_status=403, send_body=body)

    with pytest.raises(EmailSendError) as error:
        google.provider().deliver(message())

    assert error.value.transient is True


def test_missing_permission_403_fails_over_without_retrying():
    body = {
        "error": {
            "message": "Insufficient Permission",
            "errors": [{"reason": "insufficientPermissions"}],
        }
    }
    google = FakeGoogle(send_status=403, send_body=body)

    with pytest.raises(EmailSendError) as error:
        google.provider().deliver(message())

    assert error.value.transient is False
    assert error.value.failover is True


def test_invalid_message_does_not_fail_over():
    google = FakeGoogle(
        send_status=400, send_body={"error": {"message": "Invalid To header"}}
    )

    with pytest.raises(EmailSendError) as error:
        google.provider().deliver(message())

    assert error.value.failover is False
    assert error.value.transient is False


def test_unauthorized_send_drops_the_cached_token():
    google = FakeGoogle()
    provider = google.provider()
    provider.deliver(message())
    google.send_status = 401
    google.send_body = {"error": {"message": "Invalid Credentials"}}

    with pytest.raises(EmailSendError):
        provider.deliver(message())
    google.send_status = 200
    google.send_body = {"id": "msg-2"}
    provider.deliver(message())

    assert google.token_calls == 2


def test_network_error_is_transient():
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    provider = GmailProvider(config(), transport=httpx.MockTransport(broken))

    with pytest.raises(EmailSendError) as error:
        provider.deliver(message())

    assert error.value.transient is True
    assert error.value.failover is True


def test_oversized_message_is_rejected_before_calling_google():
    google = FakeGoogle()

    with pytest.raises(EmailSendError) as error:
        google.provider(max_size_mb=1).deliver(message(html="x" * (2 * 1024 * 1024)))

    assert error.value.failover is False
    assert google.token_calls == 0
