import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.email.errors import EmailSendError
from app.modules.email.failover import FailoverEmailService
from app.modules.email.protocol import EmailMessage, EmailProvider, SendResult
from app.modules.email_outbox.model import BreakerState, EmailProviderHealth

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker por provedor, com estado no banco.

    - fechado: envia normalmente;
    - aberto: após ``threshold`` falhas do provedor seguidas, o provedor é
      pulado por ``cooldown`` e o failover vai direto ao próximo;
    - meio aberto: passado o tempo, deixa um e-mail passar; sucesso fecha,
      falha abre de novo.

    Não comita: o worker grava junto com o resultado do item.
    """

    def __init__(
        self,
        db: Session,
        threshold: int,
        cooldown: timedelta,
        clock: Callable[[], datetime],
    ) -> None:
        self.db = db
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        # Provedores que abriram o circuito nesta execução (para o alerta).
        self.opened: list[str] = []

    def _health(self, provider: str) -> EmailProviderHealth:
        health = self.db.get(EmailProviderHealth, provider)
        if health is None:
            health = EmailProviderHealth(
                provider=provider, state=BreakerState.CLOSED, consecutive_failures=0
            )
            self.db.add(health)
            self.db.flush()
        return health

    def allow(self, provider: str) -> bool:
        health = self._health(provider)
        if health.state != BreakerState.OPEN:
            return True
        opened_at = health.opened_at
        if opened_at is not None and opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=self.clock().tzinfo)
        if opened_at is None or self.clock() - opened_at >= self.cooldown:
            health.state = BreakerState.HALF_OPEN
            self.db.flush()
            logger.info(
                "Email provider %s half-open, letting one email through", provider
            )
            return True
        return False

    def record_success(self, provider: str) -> None:
        health = self._health(provider)
        if health.state != BreakerState.CLOSED:
            logger.info("Email provider %s recovered, circuit closed", provider)
        health.state = BreakerState.CLOSED
        health.consecutive_failures = 0
        health.opened_at = None
        health.last_success_at = self.clock()
        self.db.flush()

    def record_failure(self, provider: str, error: str) -> None:
        health = self._health(provider)
        now = self.clock()
        health.consecutive_failures += 1
        health.last_failure_at = now
        health.last_error = error
        should_open = (
            health.state == BreakerState.HALF_OPEN
            or health.consecutive_failures >= self.threshold
        )
        if should_open and health.state != BreakerState.OPEN:
            health.state = BreakerState.OPEN
            health.opened_at = now
            self.opened.append(provider)
            logger.error(
                "Email provider %s circuit opened after %d failure(s)",
                provider,
                health.consecutive_failures,
            )
        self.db.flush()


class GuardedProvider:
    """Provedor envolvido pelo breaker. Só conta como falha do provedor o erro
    que o failover também trataria como do provedor (``failover=True``);
    destinatário recusado não abre o circuito."""

    def __init__(self, inner: EmailProvider, breaker: CircuitBreaker) -> None:
        self.inner = inner
        self.breaker = breaker
        self.name = inner.name

    def deliver(self, message: EmailMessage) -> SendResult:
        if not self.breaker.allow(self.name):
            raise EmailSendError(
                "Circuito aberto: provedor pausado após falhas seguidas",
                transient=True,
                failover=True,
                provider=self.name,
            )
        try:
            result = self.inner.deliver(message)
        except EmailSendError as err:
            if err.failover:
                self.breaker.record_failure(self.name, err.reason)
            raise
        self.breaker.record_success(self.name)
        return result

    def __enter__(self) -> "GuardedProvider":
        if hasattr(self.inner, "__enter__"):
            self.inner.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if hasattr(self.inner, "__exit__"):
            self.inner.__exit__(*exc_info)


def guard(provider: EmailProvider, breaker: CircuitBreaker) -> EmailProvider:
    """Põe o breaker na frente de cada provedor da cadeia."""
    if isinstance(provider, FailoverEmailService):
        return FailoverEmailService(
            [GuardedProvider(p, breaker) for p in provider.providers]
        )
    return GuardedProvider(provider, breaker)
