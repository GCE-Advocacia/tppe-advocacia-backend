import base64
from unittest.mock import patch

import pytest
import resend.exceptions

from app.modules.email.errors import EmailSendError
from app.modules.email.protocol import Attachment, EmailMessage
from app.modules.email.resend_provider import ResendConfig, ResendProvider

PROVIDER = ResendProvider(
    ResendConfig(api_key="re_123", from_email="noreply@x.com", from_name="Escritório")
)


@patch("app.modules.email.resend_provider.resend.Emails.send")
def test_maps_message_to_params(send):
    send.return_value = {"id": "abc"}
    message = EmailMessage(
        to=["a@b.com"],
        subject="s",
        html="<p>Oi</p>",
        bcc=["c@d.com"],
        headers={"X-Email-Id": "7"},
        attachments=[Attachment("a.pdf", "application/pdf", b"pdf")],
    )

    result = PROVIDER.deliver(message)

    params = send.call_args.args[0]
    assert params["from"] == "Escritório <noreply@x.com>"
    assert params["text"] == "Oi"
    assert params["bcc"] == ["c@d.com"]
    assert params["headers"] == {"X-Email-Id": "7"}
    assert params["attachments"][0]["content"] == base64.b64encode(b"pdf").decode()
    assert result.provider == "resend"
    assert result.message_id == "abc"


@pytest.mark.parametrize(
    "error, transient, failover",
    [
        (resend.exceptions.RateLimitError("limit", "rate_limit_exceeded", 429), True, True),
        (resend.exceptions.ApplicationError("boom", "application_error", 500), True, True),
        (resend.exceptions.InvalidApiKeyError("key", "invalid_api_key", 403), False, True),
        (resend.exceptions.ValidationError("bad", "validation_error", 422), False, False),
    ],
)
@patch("app.modules.email.resend_provider.resend.Emails.send")
def test_error_classification(send, error, transient, failover):
    send.side_effect = error
    with pytest.raises(EmailSendError) as exc:
        PROVIDER.deliver(EmailMessage(to=["a@b.com"], subject="s", html="x"))
    assert exc.value.transient is transient
    assert exc.value.failover is failover
