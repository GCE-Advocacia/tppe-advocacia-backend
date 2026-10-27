import logging
from contextlib import ExitStack

from app.modules.email.errors import EmailSendError
from app.modules.email.protocol import EmailMessage, EmailProvider, SendResult

logger = logging.getLogger(__name__)


class FailoverEmailService:
    """Tenta os provedores em ordem e passa ao próximo só quando o erro é do
    provedor (``EmailSendError.failover``). Erro do destinatário para na hora.
    """

    def __init__(self, providers: list[EmailProvider]) -> None:
        if not providers:
            raise ValueError("FailoverEmailService precisa de ao menos um provedor")
        self.providers = providers
        self._batch: ExitStack | None = None

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self.providers]

    def deliver(self, message: EmailMessage) -> SendResult:
        errors: list[EmailSendError] = []
        for provider in self.providers:
            try:
                result = provider.deliver(message)
            except EmailSendError as err:
                errors.append(err)
                if not err.failover:
                    raise
                logger.warning(
                    "Email provider %s failed (%s), trying next", provider.name, err
                )
                continue
            if errors:
                logger.info(
                    "Email delivered by fallback provider %s after %s",
                    result.provider,
                    [e.provider for e in errors],
                )
            logger.info(
                "Email sent provider=%s message_id=%s duration_ms=%d",
                result.provider,
                result.message_id,
                result.duration_ms,
            )
            return result

        last = errors[-1]
        raise EmailSendError(
            "Todos os provedores falharam: "
            + "; ".join(f"[{e.provider}] {e.reason}" for e in errors),
            # Se algum falhou por algo passageiro, a retentativa pode resolver.
            transient=any(e.transient for e in errors),
            failover=False,
            provider=last.provider,
            smtp_code=last.smtp_code,
        )

    def send(self, to: str, subject: str, html: str) -> None:
        """Atalho do contrato antigo (``EmailService.send``)."""
        self.deliver(EmailMessage(to=[to], subject=subject, html=html))

    # Lote: abre a conexão de quem suporta (SMTP) e reaproveita entre envios.
    # Falha ao abrir não impede o lote: o deliver tenta de novo e cai no
    # failover normalmente.
    def __enter__(self) -> "FailoverEmailService":
        stack = ExitStack()
        for provider in self.providers:
            if hasattr(provider, "__enter__"):
                try:
                    stack.enter_context(provider)
                except EmailSendError as err:
                    logger.warning("Could not open %s for batch: %s", provider.name, err)
        self._batch = stack
        return self

    def __exit__(self, *exc_info) -> None:
        if self._batch is not None:
            self._batch.close()
            self._batch = None
