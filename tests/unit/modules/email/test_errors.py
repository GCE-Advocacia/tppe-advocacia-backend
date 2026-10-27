import smtplib
import ssl

import pytest

from app.modules.email.errors import classify_smtp_error, enhanced_status


@pytest.mark.parametrize(
    "exc, transient, failover",
    [
        (smtplib.SMTPResponseException(421, b"4.7.0 Try again later"), True, True),
        (smtplib.SMTPResponseException(450, b"4.2.1 Mailbox busy"), True, True),
        (smtplib.SMTPResponseException(451, b"4.3.0 Local error"), True, True),
        (smtplib.SMTPResponseException(452, b"4.5.3 Too many recipients"), True, True),
        (
            smtplib.SMTPAuthenticationError(
                535, b"5.7.8 Username and Password not accepted"
            ),
            False,
            True,
        ),
        (
            smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded"),
            False,
            True,
        ),
        (smtplib.SMTPDataError(554, b"5.7.0 Message rejected by policy"), False, True),
        (smtplib.SMTPDataError(550, b"5.1.1 The email account does not exist"), False, False),
        (smtplib.SMTPDataError(553, b"5.1.3 Invalid address"), False, False),
        (smtplib.SMTPDataError(554, b"Transaction failed"), False, False),
        (smtplib.SMTPServerDisconnected("Connection unexpectedly closed"), True, True),
        (smtplib.SMTPConnectError(421, b"Service not available"), True, True),
        (TimeoutError("timed out"), True, True),
        (ConnectionRefusedError(10061, "refused"), True, True),
        (ssl.SSLCertVerificationError("bad cert"), False, True),
        (smtplib.SMTPNotSupportedError("STARTTLS extension not supported"), False, True),
    ],
)
def test_classification(exc, transient, failover):
    err = classify_smtp_error(exc, "smtp")
    assert err.transient is transient
    assert err.failover is failover
    assert err.provider == "smtp"


def test_recipients_refused_is_permanent_without_failover():
    exc = smtplib.SMTPRecipientsRefused(
        {"x@nao-existe.com": (550, b"5.1.1 User unknown")}
    )
    err = classify_smtp_error(exc)
    assert not err.transient
    assert not err.failover
    assert err.smtp_code == 550
    assert "x@nao-existe.com" in err.reason


def test_recipients_refused_by_quota_triggers_failover():
    exc = smtplib.SMTPRecipientsRefused(
        {"a@b.com": (550, b"5.4.5 Daily sending quota exceeded")}
    )
    assert classify_smtp_error(exc).failover


def test_enhanced_status_extraction():
    assert enhanced_status("5.4.5 Daily user sending limit exceeded") == "5.4.5"
    assert enhanced_status("Mailbox unavailable") is None
