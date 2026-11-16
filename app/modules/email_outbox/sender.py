from app.modules.email_outbox.model import EmailOutboxItem
from app.modules.email_outbox.service import EmailOutbox
from app.shared.db.uow import unit_of_work


class QueuedEmailSender:
    """Mesma assinatura do ``TemplatedEmailSender``, mas grava na fila em vez
    de entregar. Comita sozinho: serve para quem envia depois da própria
    transação (notificações, redefinição de senha). Quem precisa do e-mail na
    mesma transação usa ``EmailOutbox.enqueue`` direto."""

    def __init__(self, outbox: EmailOutbox) -> None:
        self.outbox = outbox

    def send(
        self,
        template_id: str,
        context: dict,
        to: str | list[str],
        *,
        related: tuple[str, int] | None = None,
        idempotency_key: str | None = None,
        created_by: int | None = None,
    ) -> EmailOutboxItem:
        with unit_of_work(self.outbox.repository.db):
            return self.outbox.enqueue(
                template_id,
                context,
                to,
                related=related,
                idempotency_key=idempotency_key,
                created_by=created_by,
            )
