from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Attachment:
    filename: str
    mime_type: str
    content: bytes


@dataclass(frozen=True)
class EmailMessage:
    to: list[str]
    subject: str
    html: str
    text: str | None = None
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    # Ex.: Message-ID, X-Email-Id (id do item na fila, para rastrear).
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def recipients(self) -> list[str]:
        """Envelope completo (to + cc + bcc)."""
        return [*self.to, *self.cc, *self.bcc]


@dataclass(frozen=True)
class SendResult:
    provider: str
    message_id: str
    duration_ms: int


class EmailProvider(Protocol):
    name: str

    def deliver(self, message: EmailMessage) -> SendResult: ...


class EmailService(Protocol):
    """Contrato antigo, mantido como atalho para os chamadores atuais."""

    def send(self, to: str, subject: str, html: str) -> None: ...
