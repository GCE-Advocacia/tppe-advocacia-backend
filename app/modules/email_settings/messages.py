"""Falha de e-mail em linguagem de quem não é técnico: o que aconteceu e o
que fazer. Usado no teste de conexão e no "Enviar teste para mim"."""

import re
import smtplib
import socket
import ssl
from dataclasses import dataclass

from app.modules.email.errors import EmailSendError
from app.modules.email_settings.presets import ProviderPreset

_CODE = re.compile(r"\b([45]\d\d)\b")


@dataclass(frozen=True)
class Explained:
    message: str
    hint: str


def _password_hint(preset: ProviderPreset | None) -> str:
    if preset is not None and preset.id in ("gmail", "outlook"):
        return (
            "Use uma senha de app, não a senha normal da conta. " + preset.password_help
        )
    return "Confira o e-mail e a senha. Se a conta usa verificação em duas etapas, crie uma senha de app."


def explain_code(
    code: int | None, raw: str, preset: ProviderPreset | None
) -> Explained:
    text = raw.lower()
    if code in (530, 534, 535) or "authentication" in text or "password" in text:
        return Explained(
            "O e-mail ou a senha não foram aceitos.", _password_hint(preset)
        )
    if code in (550, 551, 553, 554) and (
        "sender" in text or "from" in text or "5.7.1" in text or "relay" in text
    ):
        return Explained(
            "O servidor não deixou enviar com esse remetente.",
            "Use como remetente o mesmo e-mail da conta conectada.",
        )
    if code in (550, 551, 553) and (
        "recipient" in text or "user unknown" in text or "5.1.1" in text
    ):
        return Explained(
            "O endereço de destino não existe.",
            "Confira se o e-mail do destinatário está escrito certo.",
        )
    if code is not None and 400 <= code < 500:
        return Explained(
            "O servidor de e-mail está ocupado ou limitou os envios.",
            "Espere alguns minutos e tente de novo. O sistema também tenta sozinho.",
        )
    return Explained(
        "O servidor de e-mail recusou o envio.",
        "Confira os dados da conta ou fale com quem administra o e-mail do escritório.",
    )


def explain_exception(
    exc: BaseException, preset: ProviderPreset | None, port: int | None = None
) -> Explained:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return Explained(
            "O e-mail ou a senha não foram aceitos.", _password_hint(preset)
        )
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return Explained(
            "O servidor não deixou enviar com esse remetente.",
            "Use como remetente o mesmo e-mail da conta conectada.",
        )
    if isinstance(
        exc,
        smtplib.SMTPNotSupportedError | ssl.SSLError | smtplib.SMTPServerDisconnected,
    ):
        return Explained(
            "A conexão segura com o servidor não deu certo.",
            "Escolha o provedor na lista para preencher a segurança certa. Em "
            '"Outro", a porta 587 usa STARTTLS e a 465 usa SSL.',
        )
    if isinstance(exc, socket.gaierror):
        return Explained(
            "O endereço do servidor de e-mail não foi encontrado.",
            "Confira se o servidor está escrito certo (ex.: smtp.seudominio.com.br).",
        )
    if isinstance(exc, ConnectionRefusedError):
        return Explained(
            "O servidor recusou a conexão nessa porta.",
            "Confira a porta com quem administra o e-mail. As mais comuns são 587 e 465.",
        )
    if isinstance(exc, TimeoutError | socket.timeout):
        where = f"porta {port}" if port else "porta de envio"
        return Explained(
            "O servidor de e-mail não respondeu.",
            f"A {where} pode estar bloqueada pela hospedagem do sistema. Tente "
            "outra porta (587 ou 465) ou fale com o suporte.",
        )
    if isinstance(exc, smtplib.SMTPResponseException):
        error = (
            exc.smtp_error.decode(errors="replace")
            if isinstance(exc.smtp_error, bytes)
            else str(exc.smtp_error)
        )
        return explain_code(exc.smtp_code, error, preset)
    if isinstance(exc, OSError):
        return Explained(
            "Não foi possível falar com o servidor de e-mail.",
            "Confira a internet do servidor e os dados da conta e tente de novo.",
        )
    return Explained("Algo deu errado no teste.", "Tente de novo em alguns minutos.")


def explain_send_error(err: EmailSendError, preset: ProviderPreset | None) -> Explained:
    """Erro já classificado pelo provedor (só tem código e texto)."""
    code = err.smtp_code
    if code is None:
        match = _CODE.search(err.reason)
        code = int(match.group(1)) if match else None
    reason = err.reason.lower()
    if code is None:
        if "tempo" in reason or "timed out" in reason or "timeout" in reason:
            return explain_exception(TimeoutError(), preset)
        if "refused" in reason or "recusada" in reason:
            return explain_exception(ConnectionRefusedError(), preset)
        if "conexão" in reason or "connection" in reason:
            return Explained(
                "Não foi possível falar com o servidor de e-mail.",
                "Confira a internet do servidor e os dados da conta e tente de novo.",
            )
    return explain_code(code, err.reason, preset)
