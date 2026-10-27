import base64
import time
from dataclasses import dataclass

import resend
import resend.exceptions

from app.modules.email.errors import EmailSendError
from app.modules.email.mime import ensure_size_limit, html_to_text
from app.modules.email.protocol import EmailMessage, SendResult


@dataclass(frozen=True)
class ResendConfig:
    api_key: str
    from_email: str
    from_name: str | None = None
    max_size_mb: int = 10


class ResendProvider:
    """Entrega pela API do Resend. Serve de reserva para o SMTP."""

    name = "resend"

    def __init__(self, config: ResendConfig) -> None:
        self.config = config

    def _from(self) -> str:
        if self.config.from_name:
            return f"{self.config.from_name} <{self.config.from_email}>"
        return self.config.from_email

    def _params(self, message: EmailMessage) -> dict:
        params: dict = {
            "from": self._from(),
            "to": message.to,
            "subject": message.subject,
            "html": message.html,
            "text": message.text or html_to_text(message.html),
        }
        if message.cc:
            params["cc"] = message.cc
        if message.bcc:
            params["bcc"] = message.bcc
        if message.reply_to:
            params["reply_to"] = message.reply_to
        if message.headers:
            params["headers"] = dict(message.headers)
        if message.attachments:
            params["attachments"] = [
                {
                    "filename": a.filename,
                    "content": base64.b64encode(a.content).decode(),
                    "content_type": a.mime_type,
                }
                for a in message.attachments
            ]
        return params

    def deliver(self, message: EmailMessage) -> SendResult:
        ensure_size_limit(message, self.config.max_size_mb, self.name)
        started = time.monotonic()
        resend.api_key = self.config.api_key
        try:
            response = resend.Emails.send(self._params(message))
        except resend.exceptions.ResendError as exc:
            raise self._classify(exc) from exc
        except OSError as exc:
            raise EmailSendError(
                f"Erro de rede: {exc!r}",
                transient=True,
                failover=True,
                provider=self.name,
            ) from exc
        return SendResult(
            provider=self.name,
            message_id=str(response.get("id", "")),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def _classify(self, exc: resend.exceptions.ResendError) -> EmailSendError:
        try:
            code = int(exc.code)
        except (TypeError, ValueError):
            code = 0
        reason = f"Resend {exc.code}: {exc}"
        if code == 429 or code >= 500 or code == 0:
            return EmailSendError(
                reason, transient=True, failover=True, provider=self.name
            )
        if code in (401, 403):
            return EmailSendError(
                reason, transient=False, failover=True, provider=self.name
            )
        # 400/422: a mensagem em si é inválida; outro provedor não resolve.
        return EmailSendError(
            reason, transient=False, failover=False, provider=self.name
        )
