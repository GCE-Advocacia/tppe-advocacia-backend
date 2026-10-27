import uuid

from app.modules.email.errors import EmailSendError
from app.modules.email.protocol import EmailMessage, SendResult


class FakeEmailService:
    """Guarda os e-mails em memória. ``fail_with`` simula falha do provedor."""

    name = "fake"

    def __init__(self, fail_with: EmailSendError | None = None) -> None:
        self.sent: list[dict] = []
        self.messages: list[EmailMessage] = []
        self.fail_with = fail_with

    def deliver(self, message: EmailMessage) -> SendResult:
        if self.fail_with is not None:
            raise self.fail_with
        self.messages.append(message)
        for to in message.to:
            self.sent.append(
                {"to": to, "subject": message.subject, "html": message.html}
            )
        return SendResult(
            provider=self.name, message_id=f"<{uuid.uuid4()}@fake>", duration_ms=0
        )

    def send(self, to: str, subject: str, html: str) -> None:
        self.deliver(EmailMessage(to=[to], subject=subject, html=html))
