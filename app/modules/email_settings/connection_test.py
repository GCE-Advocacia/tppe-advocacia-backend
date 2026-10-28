"""Teste de conexão de um perfil, etapa por etapa, sem enviar nada.

SMTP: ``connect`` -> ``ehlo`` -> ``tls`` (STARTTLS) -> ``auth`` -> ``quit``.
No SSL (465) o TLS é negociado já no ``connect``. Para assim que uma etapa
falha e devolve o erro em linguagem clara.

Resend: uma etapa ``auth`` que valida a API key.
"""

import smtplib
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import httpx

from app.modules.email.resend_provider import ResendConfig
from app.modules.email.smtp_provider import SmtpConfig

Step = Literal["connect", "ehlo", "tls", "auth"]

_RESEND_API = "https://api.resend.com"


@dataclass
class StepResult:
    step: Step
    ok: bool
    duration_ms: int
    error: str | None = None


@dataclass
class ConnectionTestReport:
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)

    @property
    def first_error(self) -> StepResult | None:
        return next((s for s in self.steps if not s.ok), None)


def _decode(raw: bytes | str | None) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw or ""


def friendly_error(exc: BaseException, host: str = "", port: int | None = None) -> str:
    """Traduz a exceção do smtplib/socket para algo que o admin entenda."""
    where = f"{host}:{port}" if host else "o servidor"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return f"{exc.smtp_code} credenciais inválidas ({_decode(exc.smtp_error)})"
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "O servidor não oferece STARTTLS. Tente SSL (porta 465) ou outra porta."
    if isinstance(exc, ssl.SSLCertVerificationError):
        return f"Certificado TLS de {host or 'servidor'} inválido: {exc.verify_message}"
    if isinstance(exc, ssl.SSLError):
        return (
            "Falha ao negociar TLS. Confira se a segurança combina com a porta "
            "(587 = STARTTLS, 465 = SSL)."
        )
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            f"{where} fechou a conexão. Confira se a segurança combina com a "
            "porta (587 = STARTTLS, 465 = SSL)."
        )
    if isinstance(exc, smtplib.SMTPResponseException):
        return f"{exc.smtp_code} {_decode(exc.smtp_error)}".strip()
    if isinstance(exc, socket.gaierror):
        return f"Servidor {host} não encontrado. Confira o endereço."
    if isinstance(exc, TimeoutError | socket.timeout):
        return f"Tempo esgotado ao falar com {where}. Confira host, porta e firewall."
    if isinstance(exc, ConnectionRefusedError):
        return f"Conexão recusada por {where}. Confira a porta."
    if isinstance(exc, OSError):
        return f"Erro de rede ao falar com {where}: {exc}"
    return f"Erro inesperado: {exc}"


class ConnectionTester:
    """Injetável (``deps.get_connection_tester``) para os testes trocarem por
    um fake sem abrir socket."""

    def __init__(
        self,
        smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., smtplib.SMTP_SSL] = smtplib.SMTP_SSL,
        http: httpx.Client | None = None,
    ) -> None:
        self._smtp = smtp_factory
        self._smtp_ssl = smtp_ssl_factory
        self._http = http

    def test(self, config: SmtpConfig | ResendConfig) -> ConnectionTestReport:
        if isinstance(config, SmtpConfig):
            return self.test_smtp(config)
        return self.test_resend(config)

    # ---- SMTP -----------------------------------------------------------

    def test_smtp(self, cfg: SmtpConfig) -> ConnectionTestReport:
        report = ConnectionTestReport()
        context = ssl.create_default_context()
        conn: smtplib.SMTP | None = None

        def run(step: Step, action: Callable[[], object]) -> bool:
            started = time.monotonic()
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - vira mensagem para o admin
                error = friendly_error(exc, cfg.host, cfg.port)
                report.steps.append(StepResult(step, False, _elapsed(started), error))
                return False
            report.steps.append(StepResult(step, True, _elapsed(started)))
            return True

        def connect() -> None:
            nonlocal conn
            if cfg.security == "ssl":
                conn = self._smtp_ssl(
                    cfg.host, cfg.port, timeout=cfg.timeout_seconds, context=context
                )
            else:
                conn = self._smtp(cfg.host, cfg.port, timeout=cfg.timeout_seconds)

        try:
            if not run("connect", connect):
                return report
            if not run("ehlo", lambda: _check_ok(conn.ehlo())):
                return report
            if cfg.security == "starttls":

                def starttls() -> None:
                    conn.starttls(context=context)
                    conn.ehlo()

                if not run("tls", starttls):
                    return report
            if cfg.username:
                run("auth", lambda: conn.login(cfg.username, cfg.password or ""))
            return report
        finally:
            if conn is not None:
                _safe_quit(conn)

    # ---- Resend ---------------------------------------------------------

    def test_resend(self, cfg: ResendConfig) -> ConnectionTestReport:
        report = ConnectionTestReport()
        started = time.monotonic()
        client = self._http or httpx.Client(base_url=_RESEND_API, timeout=10)
        try:
            response = client.get(
                "/domains", headers={"Authorization": f"Bearer {cfg.api_key}"}
            )
        except httpx.HTTPError as exc:
            report.steps.append(
                StepResult("auth", False, _elapsed(started), f"Erro de rede: {exc}")
            )
            return report
        finally:
            if self._http is None:
                client.close()

        # Chave só de envio responde 401 restricted_api_key: é válida.
        body = _json(response)
        restricted = body.get("name") == "restricted_api_key"
        if response.is_success or restricted:
            report.steps.append(StepResult("auth", True, _elapsed(started)))
        else:
            message = body.get("message") or response.reason_phrase
            report.steps.append(
                StepResult(
                    "auth",
                    False,
                    _elapsed(started),
                    f"{response.status_code} API key recusada pelo Resend ({message})",
                )
            )
        return report


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _check_ok(reply: tuple[int, bytes]) -> None:
    code, message = reply
    if not 200 <= code < 300:
        raise smtplib.SMTPResponseException(code, message)


def _safe_quit(conn: smtplib.SMTP) -> None:
    try:
        conn.quit()
    except Exception:  # noqa: BLE001 - conexão já pode ter caído
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
