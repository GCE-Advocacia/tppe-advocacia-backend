"""Teste de conexão contra o Mailpit do docker compose (SMTP 1025).

Rode com ``docker compose up -d mailpit`` e ``pytest -m mailpit``.
"""

import os
import socket

import pytest

from app.modules.email.smtp_provider import SmtpConfig
from app.modules.email_settings.connection_test import ConnectionTester

MAILPIT_HOST = os.getenv("MAILPIT_HOST", "localhost")

pytestmark = pytest.mark.mailpit


@pytest.fixture(scope="module", autouse=True)
def mailpit_up():
    try:
        socket.create_connection((MAILPIT_HOST, 1025), timeout=2).close()
    except OSError:
        pytest.skip("Mailpit não está rodando em localhost:1025")


def _config(port: int) -> SmtpConfig:
    return SmtpConfig(
        host=MAILPIT_HOST,
        port=port,
        security="none",
        from_email="noreply@advocacia.local",
        timeout_seconds=3,
    )


def test_connection_ok():
    report = ConnectionTester().test(_config(1025))

    assert report.ok, report.steps
    assert [s.step for s in report.steps] == ["connect", "ehlo"]


def test_wrong_port_fails_at_connect():
    report = ConnectionTester().test(_config(1026))

    assert not report.ok
    assert report.first_error.step == "connect"
    assert report.first_error.error
