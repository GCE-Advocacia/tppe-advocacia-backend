import html as html_lib
import logging
import random
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.modules.email.errors import EmailSendError
from app.modules.email.protocol import EmailMessage, EmailProvider
from app.modules.email.registry import TEMPLATES
from app.modules.email.renderer import EmailRenderer, UnknownTemplateError
from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.shared.db.uow import unit_of_work

logger = logging.getLogger(__name__)

# Links com token de uso único: servem para o envio e não ficam no histórico.
SENSITIVE_CONTEXT_KEYS = ("invite_link", "reset_link")
MASK = "[link removido]"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailOutbox:
    """Grava e-mails na fila dentro da transação de quem chama.

    Não comita: se a transação do chamador desfaz, o e-mail some junto. O
    envio fica com o ``EmailOutboxWorker``, fora da requisição.
    """

    def __init__(self, repository: EmailOutboxRepository) -> None:
        self.repository = repository

    def enqueue(
        self,
        template_id: str,
        context: dict,
        to: str | list[str],
        *,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        related: tuple[str, int] | None = None,
        idempotency_key: str | None = None,
        created_by: int | None = None,
    ) -> EmailOutboxItem:
        if template_id not in TEMPLATES:
            raise UnknownTemplateError(template_id)
        if idempotency_key is not None:
            existing = self.repository.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing

        now = _utcnow()
        item = EmailOutboxItem(
            id=str(uuid.uuid4()),
            template_id=template_id,
            context=context,
            to=[to] if isinstance(to, str) else list(to),
            cc=list(cc or []),
            bcc=list(bcc or []),
            status=EmailStatus.PENDING,
            attempts=0,
            next_attempt_at=now,
            idempotency_key=idempotency_key,
            related_type=related[0] if related else None,
            related_id=related[1] if related else None,
            created_by=created_by,
            created_at=now,
        )
        if idempotency_key is None:
            return self.repository.add(item)
        # Savepoint: a corrida na chave única não derruba a transação de quem chama.
        try:
            with self.repository.db.begin_nested():
                self.repository.add(item)
        except IntegrityError:
            existing = self.repository.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return existing
        return item

    def cancel_pending(self, idempotency_key: str) -> bool:
        """Cancela o item que ainda não saiu (ex.: convite revogado antes do
        envio). Não comita."""
        item = self.repository.get_by_idempotency_key(idempotency_key)
        if item is None or item.status not in (EmailStatus.PENDING, EmailStatus.FAILED):
            return False
        item.status = EmailStatus.CANCELLED
        item.context = {
            key: (MASK if key in SENSITIVE_CONTEXT_KEYS else value)
            for key, value in item.context.items()
        }
        self.repository.db.flush()
        return True


@dataclass(frozen=True)
class RetryPolicy:
    base_seconds: int
    max_seconds: int
    max_attempts: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "RetryPolicy":
        return cls(
            base_seconds=settings.email_retry_base_seconds,
            max_seconds=settings.email_retry_max_seconds,
            max_attempts=settings.email_max_attempts,
        )

    def delay(self, attempts: int, jitter: float | None = None) -> timedelta:
        """Espera depois da tentativa ``attempts`` (1, 2, ...), com teto e
        variação de 20% para os itens não voltarem todos juntos."""
        factor = random.uniform(0.8, 1.2) if jitter is None else jitter
        seconds = min(self.base_seconds * 2 ** (attempts - 1), self.max_seconds)
        return timedelta(seconds=seconds * factor)


def _mask(value: str | None, secrets: list[str]) -> str | None:
    if value is None:
        return None
    for secret in secrets:
        value = value.replace(secret, MASK)
        value = value.replace(html_lib.escape(secret), MASK)
    return value


def _scrub(item: EmailOutboxItem, *, final: bool) -> None:
    """Mascara os links com token no corpo salvo. No fim (``SENT`` ou
    ``DEAD``) apaga também do contexto, que até lá serve à retentativa."""
    secrets = [
        str(item.context[key])
        for key in SENSITIVE_CONTEXT_KEYS
        if item.context.get(key)
    ]
    if not secrets:
        return
    item.html = _mask(item.html, secrets)
    item.text = _mask(item.text, secrets)
    item.subject = _mask(item.subject, secrets)
    if final:
        item.context = {
            key: (MASK if key in SENSITIVE_CONTEXT_KEYS else value)
            for key, value in item.context.items()
        }


class EmailOutboxWorker:
    """Envia o que está pronto na fila. Roda no serviço ``scheduler``.

    Cada lote é reservado numa transação curta (``SENDING``) e cada item tem
    o resultado gravado na sua própria transação, então um item que falha não
    desfaz os outros.
    """

    def __init__(
        self,
        repository: EmailOutboxRepository,
        renderer: EmailRenderer,
        provider: EmailProvider,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = _utcnow,
        worker_id: str | None = None,
    ) -> None:
        self.repository = repository
        self.renderer = renderer
        self.provider = provider
        self.batch_size = settings.email_outbox_batch_size
        self.stuck_after = timedelta(minutes=settings.email_outbox_stuck_minutes)
        self.retry = RetryPolicy.from_settings(settings)
        self.clock = clock
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"

    @property
    def db(self):
        return self.repository.db

    def run_once(self) -> int:
        """Processa um lote e devolve quantos e-mails saíram."""
        now = self.clock()
        with unit_of_work(self.db):
            released = self.repository.release_stuck(now - self.stuck_after, now)
            items = self.repository.claim_ready(now, self.batch_size, self.worker_id)
        if released:
            logger.warning("Email outbox: %d stuck item(s) returned to queue", released)

        sent = 0
        for item in items:
            if self._deliver(item):
                sent += 1
        return sent

    def _deliver(self, item: EmailOutboxItem) -> bool:
        attempt_at = self.clock()
        error: str | None = None
        retry = False
        try:
            rendered = self.renderer.render(item.template_id, item.context)
            item.subject, item.html, item.text = (
                rendered.subject,
                rendered.html,
                rendered.text,
            )
            result = self.provider.deliver(
                EmailMessage(
                    to=list(item.to),
                    cc=list(item.cc or []),
                    bcc=list(item.bcc or []),
                    subject=rendered.subject,
                    html=rendered.html,
                    text=rendered.text,
                    headers={"X-Email-Id": item.id},
                )
            )
        except EmailSendError as exc:
            error, retry = repr(exc), exc.transient
            item.provider = exc.provider
        except Exception as exc:  # noqa: BLE001 - template quebrado não trava a fila
            logger.exception("Email %s could not be rendered or sent", item.id)
            error, retry = f"{type(exc).__name__}: {exc}", False

        item.attempts += 1
        item.locked_at = None
        item.locked_by = None
        if error is None:
            item.status = EmailStatus.SENT
            item.sent_at = attempt_at
            item.provider = result.provider
            item.provider_message_id = result.message_id
            item.last_error = None
        elif retry and item.attempts < self.retry.max_attempts:
            item.status = EmailStatus.FAILED
            item.last_error = error
            item.next_attempt_at = attempt_at + self.retry.delay(item.attempts)
        else:
            item.status = EmailStatus.DEAD
            item.last_error = error
            logger.error("Email %s is DEAD after %d attempt(s)", item.id, item.attempts)

        _scrub(item, final=item.status != EmailStatus.FAILED)
        with unit_of_work(self.db):
            self.db.flush()
        return error is None
