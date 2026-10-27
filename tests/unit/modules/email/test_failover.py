import pytest

from app.modules.email.errors import EmailSendError
from app.modules.email.failover import FailoverEmailService
from app.modules.email.protocol import EmailMessage, SendResult

MESSAGE = EmailMessage(to=["cliente@exemplo.com"], subject="s", html="<p>x</p>")


class StubProvider:
    def __init__(self, name: str, error: EmailSendError | None = None) -> None:
        self.name = name
        self.error = error
        self.calls = 0

    def deliver(self, message: EmailMessage) -> SendResult:
        self.calls += 1
        if self.error:
            raise self.error
        return SendResult(provider=self.name, message_id="<id>", duration_ms=1)


def _err(provider: str, *, transient: bool, failover: bool, code=None) -> EmailSendError:
    return EmailSendError(
        "falha", transient=transient, failover=failover, provider=provider,
        smtp_code=code,
    )


def test_primary_ok_does_not_touch_backup():
    primary, backup = StubProvider("smtp"), StubProvider("resend")
    result = FailoverEmailService([primary, backup]).deliver(MESSAGE)
    assert result.provider == "smtp"
    assert backup.calls == 0


def test_timeout_on_primary_goes_to_backup():
    primary = StubProvider("smtp", _err("smtp", transient=True, failover=True))
    backup = StubProvider("resend")
    result = FailoverEmailService([primary, backup]).deliver(MESSAGE)
    assert result.provider == "resend"
    assert primary.calls == backup.calls == 1


def test_auth_error_on_primary_goes_to_backup():
    primary = StubProvider("smtp", _err("smtp", transient=False, failover=True, code=535))
    backup = StubProvider("resend")
    assert FailoverEmailService([primary, backup]).deliver(MESSAGE).provider == "resend"


def test_recipient_error_does_not_try_backup():
    error = _err("smtp", transient=False, failover=False, code=550)
    primary, backup = StubProvider("smtp", error), StubProvider("resend")
    with pytest.raises(EmailSendError) as exc:
        FailoverEmailService([primary, backup]).deliver(MESSAGE)
    assert exc.value is error
    assert backup.calls == 0


def test_all_fail_keeps_transient_if_any_was_transient():
    primary = StubProvider("smtp", _err("smtp", transient=True, failover=True))
    backup = StubProvider("resend", _err("resend", transient=False, failover=True))
    with pytest.raises(EmailSendError) as exc:
        FailoverEmailService([primary, backup]).deliver(MESSAGE)
    assert exc.value.transient
    assert not exc.value.failover
    assert "[smtp]" in exc.value.reason and "[resend]" in exc.value.reason


def test_all_fail_permanently():
    primary = StubProvider("smtp", _err("smtp", transient=False, failover=True))
    backup = StubProvider("resend", _err("resend", transient=False, failover=True))
    with pytest.raises(EmailSendError) as exc:
        FailoverEmailService([primary, backup]).deliver(MESSAGE)
    assert not exc.value.transient


def test_legacy_send_shortcut():
    primary = StubProvider("smtp")
    FailoverEmailService([primary]).send("a@b.com", "s", "<p>x</p>")
    assert primary.calls == 1


def test_requires_a_provider():
    with pytest.raises(ValueError):
        FailoverEmailService([])
