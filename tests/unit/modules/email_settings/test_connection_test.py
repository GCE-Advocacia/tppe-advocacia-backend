import smtplib
import socket
from unittest.mock import MagicMock

import httpx

from app.modules.email.resend_provider import ResendConfig
from app.modules.email.smtp_provider import SmtpConfig
from app.modules.email_settings.connection_test import ConnectionTester


def _config(**overrides) -> SmtpConfig:
    data = {
        "host": "smtp.gmail.com",
        "port": 587,
        "security": "starttls",
        "username": "conta@gmail.com",
        "password": "senha",
        "from_email": "conta@gmail.com",
    }
    data.update(overrides)
    return SmtpConfig(**data)


def _conn() -> MagicMock:
    conn = MagicMock()
    conn.ehlo.return_value = (250, b"OK")
    return conn


def _tester(conn=None, error: Exception | None = None):
    smtp = MagicMock(side_effect=error) if error else MagicMock(return_value=conn)
    smtp_ssl = MagicMock(return_value=conn)
    return (
        ConnectionTester(smtp_factory=smtp, smtp_ssl_factory=smtp_ssl),
        smtp,
        smtp_ssl,
    )


def test_starttls_runs_every_step_and_sends_nothing():
    conn = _conn()
    tester, smtp, _ = _tester(conn)

    report = tester.test(_config())

    assert report.ok
    assert [s.step for s in report.steps] == ["connect", "ehlo", "tls", "auth"]
    conn.starttls.assert_called_once()
    conn.login.assert_called_once_with("conta@gmail.com", "senha")
    conn.send_message.assert_not_called()
    conn.sendmail.assert_not_called()
    conn.quit.assert_called_once()


def test_ssl_uses_smtp_ssl_without_starttls():
    conn = _conn()
    tester, smtp, smtp_ssl = _tester(conn)

    report = tester.test(_config(port=465, security="ssl"))

    assert report.ok
    smtp_ssl.assert_called_once()
    smtp.assert_not_called()
    assert [s.step for s in report.steps] == ["connect", "ehlo", "auth"]


def test_no_username_skips_auth():
    tester, _, _ = _tester(_conn())

    report = tester.test(_config(security="none", username=None))

    assert [s.step for s in report.steps] == ["connect", "ehlo"]


def test_refused_port_stops_at_connect():
    tester, _, _ = _tester(error=ConnectionRefusedError())

    report = tester.test(_config(port=2626))

    assert not report.ok
    assert len(report.steps) == 1
    assert report.steps[0].step == "connect"
    assert "Conexão recusada" in report.steps[0].error
    assert "smtp.gmail.com:2626" in report.steps[0].error


def test_unknown_host_message():
    tester, _, _ = _tester(error=socket.gaierror())

    report = tester.test(_config(host="naoexiste.invalid"))

    assert "não encontrado" in report.steps[0].error


def test_bad_credentials_fail_at_auth_and_quit():
    conn = _conn()
    conn.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 bad")
    tester, _, _ = _tester(conn)

    report = tester.test(_config())

    assert not report.ok
    assert report.first_error.step == "auth"
    assert report.first_error.error.startswith("535 credenciais inválidas")
    conn.quit.assert_called_once()


def _resend(status: int, body: dict) -> ConnectionTester:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    client = httpx.Client(base_url="https://api.resend.com", transport=transport)
    return ConnectionTester(http=client)


def test_resend_valid_key():
    report = _resend(200, {"data": []}).test(
        ResendConfig(api_key="re_1", from_email="a@a.com")
    )
    assert report.ok


def test_resend_send_only_key_is_valid():
    report = _resend(401, {"name": "restricted_api_key", "message": "x"}).test(
        ResendConfig(api_key="re_1", from_email="a@a.com")
    )
    assert report.ok


def test_resend_invalid_key():
    report = _resend(
        401, {"name": "validation_error", "message": "API key is invalid"}
    ).test(ResendConfig(api_key="re_1", from_email="a@a.com"))
    assert not report.ok
    assert "API key is invalid" in report.steps[0].error
