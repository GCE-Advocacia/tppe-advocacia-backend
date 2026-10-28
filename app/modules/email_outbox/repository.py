from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus

_READY = (EmailStatus.PENDING, EmailStatus.FAILED)


class EmailOutboxRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e quem orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, item: EmailOutboxItem) -> EmailOutboxItem:
        self.db.add(item)
        self.db.flush()
        return item

    def get(self, item_id: str) -> EmailOutboxItem | None:
        return self.db.get(EmailOutboxItem, item_id)

    def get_by_idempotency_key(self, key: str) -> EmailOutboxItem | None:
        return self.db.scalars(
            select(EmailOutboxItem).where(EmailOutboxItem.idempotency_key == key)
        ).first()

    def claim_ready(
        self, now: datetime, limit: int, worker_id: str
    ) -> list[EmailOutboxItem]:
        """Marca um lote como ``SENDING``. ``SKIP LOCKED`` faz dois workers
        pegarem lotes diferentes no Postgres (o SQLite ignora a cláusula)."""
        items = list(
            self.db.scalars(
                select(EmailOutboxItem)
                .where(
                    EmailOutboxItem.status.in_(_READY),
                    EmailOutboxItem.next_attempt_at <= now,
                )
                .order_by(EmailOutboxItem.next_attempt_at, EmailOutboxItem.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
        )
        for item in items:
            item.status = EmailStatus.SENDING
            item.locked_at = now
            item.locked_by = worker_id
        self.db.flush()
        return items

    def release_stuck(self, locked_before: datetime, now: datetime) -> int:
        """Devolve à fila o que ficou em ``SENDING`` (worker caiu no meio)."""
        result = self.db.execute(
            update(EmailOutboxItem)
            .where(
                EmailOutboxItem.status == EmailStatus.SENDING,
                EmailOutboxItem.locked_at < locked_before,
            )
            .values(
                status=EmailStatus.FAILED,
                next_attempt_at=now,
                locked_at=None,
                locked_by=None,
                last_error="Envio interrompido; devolvido à fila",
            )
        )
        return result.rowcount or 0

    def list_related(
        self, related_type: str, related_ids: list[int], template_id: str
    ) -> list[EmailOutboxItem]:
        if not related_ids:
            return []
        return list(
            self.db.scalars(
                select(EmailOutboxItem)
                .where(
                    EmailOutboxItem.related_type == related_type,
                    EmailOutboxItem.related_id.in_(related_ids),
                    EmailOutboxItem.template_id == template_id,
                )
                .order_by(EmailOutboxItem.created_at.asc())
            ).all()
        )
