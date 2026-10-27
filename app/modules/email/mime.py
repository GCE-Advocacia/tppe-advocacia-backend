"""Montagem da mensagem MIME a partir do ``EmailMessage`` do contrato."""

import email.message
import email.utils
from html.parser import HTMLParser

from app.modules.email.errors import EmailSendError
from app.modules.email.protocol import EmailMessage

_BLOCK_TAGS = {"p", "div", "br", "tr", "h1", "h2", "h3", "h4", "li", "table"}
_SKIP_TAGS = {"style", "script", "head", "title"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Fallback para quando o chamador não manda a versão em texto."""
    parser = _TextExtractor()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def sender_domain(from_email: str) -> str:
    return from_email.rsplit("@", 1)[-1] if "@" in from_email else "localhost"


def build_mime(
    message: EmailMessage, from_email: str, from_name: str | None = None
) -> email.message.EmailMessage:
    mime = email.message.EmailMessage()
    mime["From"] = email.utils.formataddr((from_name or "", from_email))
    mime["To"] = ", ".join(message.to)
    if message.cc:
        mime["Cc"] = ", ".join(message.cc)
    # Bcc não entra no cabeçalho: só no envelope (EmailMessage.recipients).
    if message.reply_to:
        mime["Reply-To"] = message.reply_to
    mime["Subject"] = message.subject
    mime["Date"] = email.utils.formatdate(localtime=False)

    headers = dict(message.headers)
    mime["Message-ID"] = headers.pop("Message-ID", None) or email.utils.make_msgid(
        domain=sender_domain(from_email)
    )
    for name, value in headers.items():
        mime[name] = value

    mime.set_content(message.text or html_to_text(message.html))
    mime.add_alternative(message.html, subtype="html")
    # add_attachment transforma em multipart/mixed com o alternative dentro.
    for attachment in message.attachments:
        maintype, _, subtype = attachment.mime_type.partition("/")
        mime.add_attachment(
            attachment.content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )
    return mime


def ensure_size_limit(message: EmailMessage, max_size_mb: int, provider: str) -> None:
    """Valida antes de conectar: anexos + corpo, sem o overhead do base64."""
    total = (
        len(message.html.encode())
        + len((message.text or "").encode())
        + sum(len(a.content) for a in message.attachments)
    )
    limit = max_size_mb * 1024 * 1024
    if total > limit:
        raise EmailSendError(
            f"Mensagem com {total / 1024 / 1024:.1f} MB excede o limite de "
            f"{max_size_mb} MB",
            transient=False,
            failover=False,
            provider=provider,
        )
