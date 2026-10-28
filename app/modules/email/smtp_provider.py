import logging
import smtplib
import ssl
import time
from dataclasses import dataclass
from typing import Literal

from app.modules.email.errors import classify_smtp_error
from app.modules.email.mime import build_mime, ensure_size_limit
from app.modules.email.protocol import EmailMessage, SendResult

logger = logging.getLogger(__name__)

SmtpSecurity = Literal["starttls", "ssl", "none"]


@dataclass(frozen=True)
class SmtpConfig:
    """Configuração pronta de um servidor SMTP.

    Não lê ``get_settings()``: quem monta é a fábrica (a partir do ``.env``)
    ou, depois, a configuração salva no banco.
    """

    host: str
    port: int
    from_email: str
    security: SmtpSecurity = "starttls"
    username: str | None = None
    password: str | None = None
    from_name: str | None = None
    # Responder-para padrão do perfil; o da mensagem tem prioridade.
    reply_to: str | None = None
    timeout_seconds: float = 15.0
    max_size_mb: int = 10


class SmtpProvider:
    """Entrega por SMTP (STARTTLS na 587, SSL na 465, ou sem TLS no Mailpit).

    Fora de um lote, cada ``deliver`` abre e fecha a conexão. Dentro de um
    lote (``with provider:``), a conexão é reaproveitada e checada com
    ``noop()`` antes de cada envio.
    """

    name = "smtp"

    def __init__(self, config: SmtpConfig) -> None:
        self.config = config
        self._conn: smtplib.SMTP | None = None

    # ---- conexão --------------------------------------------------------

    def _connect(self) -> smtplib.SMTP:
        cfg = self.config
        context = ssl.create_default_context()
        if cfg.security == "ssl":
            conn: smtplib.SMTP = smtplib.SMTP_SSL(
                cfg.host, cfg.port, timeout=cfg.timeout_seconds, context=context
            )
        else:
            conn = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout_seconds)
        try:
            conn.ehlo()
            if cfg.security == "starttls":
                conn.starttls(context=context)
                conn.ehlo()
            if cfg.username:
                conn.login(cfg.username, cfg.password or "")
        except BaseException:
            self._safe_quit(conn)
            raise
        return conn

    @staticmethod
    def _safe_quit(conn: smtplib.SMTP) -> None:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001 - conexão já pode ter caído
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _alive(self, conn: smtplib.SMTP) -> bool:
        try:
            return conn.noop()[0] == 250
        except Exception:  # noqa: BLE001
            return False

    def open(self) -> None:
        if self._conn is None:
            try:
                self._conn = self._connect()
            except Exception as exc:
                raise classify_smtp_error(exc, self.name) from exc

    def close(self) -> None:
        if self._conn is not None:
            self._safe_quit(self._conn)
            self._conn = None

    def __enter__(self) -> "SmtpProvider":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ---- envio ----------------------------------------------------------

    def deliver(self, message: EmailMessage) -> SendResult:
        ensure_size_limit(message, self.config.max_size_mb, self.name)
        mime = build_mime(
            message,
            self.config.from_email,
            self.config.from_name,
            default_reply_to=self.config.reply_to,
        )
        started = time.monotonic()

        in_batch = self._conn is not None
        conn: smtplib.SMTP | None = None
        try:
            if in_batch and not self._alive(self._conn):
                logger.info("SMTP connection dropped, reconnecting")
                self.close()
                self._conn = self._connect()
            conn = self._conn if in_batch else self._connect()
            refused = conn.send_message(
                mime, from_addr=self.config.from_email, to_addrs=message.recipients
            )
        except Exception as exc:
            if in_batch:
                self.close()
            elif conn is not None:
                self._safe_quit(conn)
            raise classify_smtp_error(exc, self.name) from exc

        # Daqui em diante o servidor já aceitou o DATA: nenhuma falha pode
        # virar erro, senão o failover mandaria o mesmo e-mail duas vezes.
        if not in_batch:
            self._safe_quit(conn)
        if refused:
            logger.warning("SMTP accepted message but refused %s", refused)

        return SendResult(
            provider=self.name,
            message_id=str(mime["Message-ID"]),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
