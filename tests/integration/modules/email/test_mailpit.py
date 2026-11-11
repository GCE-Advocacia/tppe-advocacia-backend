"""Envio real contra o Mailpit do docker compose (SMTP 1025, API 8025).

Rode com ``docker compose up -d mailpit`` e ``pytest -m mailpit``. Sem o
Mailpit no ar, os testes são pulados.
"""

import os
import uuid

import httpx
import pytest

from app.modules.email.failover import FailoverEmailService
from app.modules.email.protocol import Attachment, EmailMessage
from app.modules.email.smtp_provider import SmtpConfig, SmtpProvider

MAILPIT_HOST = os.getenv("MAILPIT_HOST", "localhost")
MAILPIT_API = f"http://{MAILPIT_HOST}:8025/api/v1"

pytestmark = pytest.mark.mailpit


@pytest.fixture(scope="module")
def mailpit() -> httpx.Client:
    client = httpx.Client(base_url=MAILPIT_API, timeout=5)
    try:
        client.get("/messages", params={"limit": 1}).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Mailpit não está rodando em localhost:8025")
    return client


def _provider() -> SmtpProvider:
    return SmtpProvider(
        SmtpConfig(
            host=MAILPIT_HOST,
            port=1025,
            security="none",
            from_email="noreply@advocacia.local",
            from_name="Escritório Teste",
        )
    )


def _find(mailpit: httpx.Client, subject: str) -> dict:
    found = mailpit.get("/search", params={"query": f'subject:"{subject}"'}).json()
    assert found["messages"], f"e-mail '{subject}' não chegou ao Mailpit"
    return mailpit.get(f"/message/{found['messages'][0]['ID']}").json()


def test_message_arrives_with_attachment_and_headers(mailpit):
    subject = f"Teste {uuid.uuid4()}"
    email_id = str(uuid.uuid4())
    result = FailoverEmailService([_provider()]).deliver(
        EmailMessage(
            to=["cliente@exemplo.com"],
            subject=subject,
            html="<p>Olá <b>Maria</b></p>",
            text="Olá Maria",
            attachments=[Attachment("contrato.pdf", "application/pdf", b"%PDF-1.4")],
            headers={"X-Email-Id": email_id},
        )
    )

    message = _find(mailpit, subject)
    assert result.provider == "smtp"
    assert message["Subject"] == subject
    assert message["Text"].strip() == "Olá Maria"
    assert "<b>Maria</b>" in message["HTML"]
    assert [a["FileName"] for a in message["Attachments"]] == ["contrato.pdf"]
    assert message["MessageID"] == result.message_id.strip("<>")

    headers = mailpit.get(f"/message/{message['ID']}/headers").json()
    assert headers["X-Email-Id"] == [email_id]


def test_batch_reuses_connection(mailpit):
    tag = uuid.uuid4()
    with _provider() as provider:
        for i in range(3):
            provider.deliver(
                EmailMessage(to=["a@b.com"], subject=f"Lote {tag} {i}", html="<p>x</p>")
            )
    for i in range(3):
        _find(mailpit, f"Lote {tag} {i}")
