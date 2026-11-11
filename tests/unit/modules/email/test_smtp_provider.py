import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.modules.email.errors import EmailSendError
from app.modules.email.protocol import EmailMessage
from app.modules.email.smtp_provider import SmtpConfig, SmtpProvider

MESSAGE = EmailMessage(
    to=["cliente@exemplo.com"],
    bcc=["arquivo@escritorio.com"],
    subject="Assunto",
    html="<p>Oi</p>",
)


def _config(**overrides) -> SmtpConfig:
    data = {
        "host": "smtp.gmail.com",
        "port": 587,
        "security": "starttls",
        "username": "conta@gmail.com",
        "password": "senha-de-app",
        "from_email": "conta@gmail.com",
    }
    data.update(overrides)
    return SmtpConfig(**data)


def _conn() -> MagicMock:
    conn = MagicMock()
    conn.noop.return_value = (250, b"OK")
    conn.send_message.return_value = {}
    return conn


@pytest.fixture
def smtp():
    with patch("app.modules.email.smtp_provider.smtplib.SMTP") as smtp_cls, patch(
        "app.modules.email.smtp_provider.smtplib.SMTP_SSL"
    ) as ssl_cls:
        smtp_cls.return_value = _conn()
        ssl_cls.return_value = _conn()
        yield smtp_cls, ssl_cls


class TestConnection:
    def test_starttls_on_587(self, smtp):
        smtp_cls, ssl_cls = smtp
        result = SmtpProvider(_config()).deliver(MESSAGE)

        smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=15.0)
        ssl_cls.assert_not_called()
        conn = smtp_cls.return_value
        conn.starttls.assert_called_once()
        conn.login.assert_called_once_with("conta@gmail.com", "senha-de-app")
        conn.quit.assert_called_once()
        assert result.provider == "smtp"
        assert result.message_id.endswith("@gmail.com>")

    def test_ssl_on_465(self, smtp):
        smtp_cls, ssl_cls = smtp
        SmtpProvider(_config(port=465, security="ssl")).deliver(MESSAGE)

        smtp_cls.assert_not_called()
        assert ssl_cls.call_args.args == ("smtp.gmail.com", 465)
        ssl_cls.return_value.starttls.assert_not_called()

    def test_no_tls_no_auth_for_mailpit(self, smtp):
        smtp_cls, _ = smtp
        SmtpProvider(
            _config(host="mailpit", port=1025, security="none", username=None)
        ).deliver(MESSAGE)

        conn = smtp_cls.return_value
        conn.starttls.assert_not_called()
        conn.login.assert_not_called()

    def test_envelope_includes_bcc(self, smtp):
        smtp_cls, _ = smtp
        SmtpProvider(_config()).deliver(MESSAGE)

        kwargs = smtp_cls.return_value.send_message.call_args.kwargs
        assert kwargs["to_addrs"] == ["cliente@exemplo.com", "arquivo@escritorio.com"]
        assert kwargs["from_addr"] == "conta@gmail.com"


class TestBatch:
    def test_reuses_connection(self, smtp):
        smtp_cls, _ = smtp
        with SmtpProvider(_config()) as provider:
            provider.deliver(MESSAGE)
            provider.deliver(MESSAGE)

        assert smtp_cls.call_count == 1
        conn = smtp_cls.return_value
        assert conn.send_message.call_count == 2
        assert conn.noop.call_count == 2
        conn.quit.assert_called_once()

    def test_reconnects_when_noop_fails(self, smtp):
        smtp_cls, _ = smtp
        dead, fresh = _conn(), _conn()
        dead.noop.side_effect = smtplib.SMTPServerDisconnected()
        smtp_cls.side_effect = [dead, fresh]

        with SmtpProvider(_config()) as provider:
            provider.deliver(MESSAGE)

        dead.send_message.assert_not_called()
        fresh.send_message.assert_called_once()


class TestErrors:
    def test_auth_error_is_classified(self, smtp):
        smtp_cls, _ = smtp
        smtp_cls.return_value.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"5.7.8 Username and Password not accepted"
        )
        with pytest.raises(EmailSendError) as exc:
            SmtpProvider(_config()).deliver(MESSAGE)
        assert exc.value.smtp_code == 535
        assert exc.value.failover and not exc.value.transient
        smtp_cls.return_value.quit.assert_called()

    def test_error_on_quit_after_send_is_not_a_failure(self, smtp):
        smtp_cls, _ = smtp
        conn = smtp_cls.return_value
        conn.quit.side_effect = smtplib.SMTPServerDisconnected()

        result = SmtpProvider(_config()).deliver(MESSAGE)

        assert result.provider == "smtp"
        conn.close.assert_called()

    def test_timeout_on_connect(self, smtp):
        smtp_cls, _ = smtp
        smtp_cls.side_effect = TimeoutError("timed out")
        with pytest.raises(EmailSendError) as exc:
            SmtpProvider(_config()).deliver(MESSAGE)
        assert exc.value.transient and exc.value.failover

    def test_size_limit_checked_before_connecting(self, smtp):
        smtp_cls, _ = smtp
        big = EmailMessage(to=["a@b.com"], subject="s", html="x" * (2 * 1024 * 1024))
        with pytest.raises(EmailSendError):
            SmtpProvider(_config(max_size_mb=1)).deliver(big)
        smtp_cls.assert_not_called()
