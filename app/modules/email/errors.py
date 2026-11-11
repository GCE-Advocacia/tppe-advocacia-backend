"""Erros de envio e classificação dos erros de SMTP.

Duas perguntas diferentes, dois campos:

- ``transient``: vale tentar de novo mais tarde? (usado pela retentativa)
- ``failover``: o problema é do provedor, então outro provedor pode entregar?
  (usado pelo ``FailoverEmailService``)

Ex.: 535 (credencial inválida) não melhora sozinho, mas o reserva entrega;
550 5.1.1 (destinatário inexistente) não adianta tentar em lugar nenhum.
"""

import re
import smtplib
import ssl

_ENHANCED_STATUS = re.compile(r"\b([245])\.(\d{1,3})\.(\d{1,3})\b")

# Classes de status estendido (RFC 3463) que indicam problema do provedor
# (cota, política, autenticação), e não do destinatário.
_PROVIDER_SIDE_PREFIXES = ("5.4.", "5.7.")


class EmailSendError(Exception):
    def __init__(
        self,
        reason: str,
        *,
        transient: bool,
        failover: bool,
        provider: str,
        smtp_code: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.transient = transient
        self.failover = failover
        self.provider = provider
        self.smtp_code = smtp_code

    def __repr__(self) -> str:
        return (
            f"EmailSendError(provider={self.provider!r}, code={self.smtp_code}, "
            f"transient={self.transient}, failover={self.failover}, "
            f"reason={self.reason!r})"
        )


def _decode(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


def enhanced_status(message: str) -> str | None:
    match = _ENHANCED_STATUS.search(message)
    return ".".join(match.groups()) if match else None


def classify_smtp_response(code: int, message: str, provider: str) -> EmailSendError:
    """Classifica uma resposta do servidor (código + texto)."""
    reason = f"{code} {message}".strip()
    if 400 <= code < 500:
        return EmailSendError(
            reason, transient=True, failover=True, provider=provider, smtp_code=code
        )

    status = enhanced_status(message)
    if status is not None:
        provider_side = status.startswith(_PROVIDER_SIDE_PREFIXES)
    else:
        provider_side = code in (530, 534, 535)
    return EmailSendError(
        reason, transient=False, failover=provider_side, provider=provider,
        smtp_code=code,
    )


def classify_smtp_error(exc: BaseException, provider: str = "smtp") -> EmailSendError:
    if isinstance(exc, EmailSendError):
        return exc

    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        # Todos os destinatários recusados. Se algum foi por cota/política,
        # é o provedor que está recusando, e não o endereço.
        errors = [
            classify_smtp_response(code, _decode(msg), provider)
            for code, msg in exc.recipients.values()
        ]
        detail = "; ".join(
            f"{addr}: {code} {_decode(msg)}"
            for addr, (code, msg) in exc.recipients.items()
        )
        return EmailSendError(
            f"Destinatários recusados ({detail})",
            transient=any(e.transient for e in errors),
            failover=any(e.failover for e in errors),
            provider=provider,
            smtp_code=errors[0].smtp_code if errors else None,
        )

    if isinstance(exc, smtplib.SMTPServerDisconnected | smtplib.SMTPConnectError):
        return EmailSendError(
            f"Conexão com o servidor falhou: {exc}",
            transient=True,
            failover=True,
            provider=provider,
            smtp_code=getattr(exc, "smtp_code", None),
        )

    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return EmailSendError(
            f"Autenticação recusada: {exc.smtp_code} {_decode(exc.smtp_error)}",
            transient=False,
            failover=True,
            provider=provider,
            smtp_code=exc.smtp_code,
        )

    if isinstance(exc, smtplib.SMTPResponseException):
        return classify_smtp_response(exc.smtp_code, _decode(exc.smtp_error), provider)

    if isinstance(exc, smtplib.SMTPNotSupportedError):
        # Ex.: servidor sem STARTTLS. É configuração, não o destinatário.
        return EmailSendError(
            f"Recurso não suportado pelo servidor: {exc}",
            transient=False,
            failover=True,
            provider=provider,
        )

    if isinstance(exc, ssl.SSLCertVerificationError):
        return EmailSendError(
            f"Certificado TLS inválido: {exc}",
            transient=False,
            failover=True,
            provider=provider,
        )

    if isinstance(exc, OSError):
        # Timeout, conexão recusada, DNS, TLS interrompido.
        return EmailSendError(
            f"Erro de rede: {exc!r}",
            transient=True,
            failover=True,
            provider=provider,
        )

    if isinstance(exc, smtplib.SMTPException):
        return EmailSendError(
            f"Erro SMTP: {exc}", transient=False, failover=True, provider=provider
        )

    return EmailSendError(
        f"Erro inesperado: {exc!r}", transient=False, failover=False, provider=provider
    )
