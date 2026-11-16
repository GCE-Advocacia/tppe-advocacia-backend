from datetime import datetime

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.orm import Session, load_only

from app.modules.email_outbox.model import (
    EmailAttempt,
    EmailOutboxItem,
    EmailProviderHealth,
    EmailStatus,
)

_READY = (EmailStatus.PENDING, EmailStatus.FAILED)
FINAL = (EmailStatus.SENT, EmailStatus.DEAD, EmailStatus.CANCELLED)


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

    def add_attempt(self, attempt: EmailAttempt) -> EmailAttempt:
        self.db.add(attempt)
        self.db.flush()
        return attempt

    def count_attempts_since(self, since: datetime) -> int:
        return (
            self.db.scalar(
                select(func.count(EmailAttempt.id)).where(
                    EmailAttempt.created_at >= since
                )
            )
            or 0
        )

    def purge_bodies(self, before: datetime) -> int:
        result = self.db.execute(
            update(EmailOutboxItem)
            .where(
                EmailOutboxItem.status.in_(FINAL),
                EmailOutboxItem.created_at < before,
                EmailOutboxItem.html.is_not(None),
            )
            .values(html=None, text=None, context={})
        )
        return result.rowcount or 0

    def count_backlog(self, created_before: datetime) -> int:
        """Itens que ainda não saíram e estão na fila desde antes de
        ``created_before``."""
        return (
            self.db.scalar(
                select(func.count(EmailOutboxItem.id)).where(
                    EmailOutboxItem.status.in_((*_READY, EmailStatus.SENDING)),
                    EmailOutboxItem.created_at < created_before,
                )
            )
            or 0
        )

    def list_unsent_related(
        self, related_type: str, related_id: int
    ) -> list[EmailOutboxItem]:
        return list(
            self.db.scalars(
                select(EmailOutboxItem).where(
                    EmailOutboxItem.related_type == related_type,
                    EmailOutboxItem.related_id == related_id,
                    EmailOutboxItem.status.in_(_READY),
                )
            ).all()
        )

    def search(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        status: EmailStatus | None,
        template: str | None,
        search: str | None,
        related_type: str | None,
        related_id: int | None,
        page: int,
        limit: int,
    ) -> tuple[list[EmailOutboxItem], int]:
        stmt = select(EmailOutboxItem)
        if start is not None:
            stmt = stmt.where(EmailOutboxItem.created_at >= start)
        if end is not None:
            stmt = stmt.where(EmailOutboxItem.created_at < end)
        if status is not None:
            stmt = stmt.where(EmailOutboxItem.status == status)
        if template:
            # "notification" pega todos os notification.*.
            stmt = stmt.where(
                or_(
                    EmailOutboxItem.template_id == template,
                    EmailOutboxItem.template_id.like(f"{template}.%"),
                )
            )
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    cast(EmailOutboxItem.to, String).ilike(term),
                    EmailOutboxItem.subject.ilike(term),
                )
            )
        if related_type is not None:
            stmt = stmt.where(EmailOutboxItem.related_type == related_type)
        if related_id is not None:
            stmt = stmt.where(EmailOutboxItem.related_id == related_id)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self.db.scalars(
            stmt.order_by(EmailOutboxItem.created_at.desc(), EmailOutboxItem.id)
            .offset((page - 1) * limit)
            .limit(limit)
        ).all()
        return list(items), total

    def list_by_ids(self, ids: list[str]) -> list[EmailOutboxItem]:
        return list(
            self.db.scalars(
                select(EmailOutboxItem).where(EmailOutboxItem.id.in_(ids))
            ).all()
        )

    def list_attempts(self, email_id: str) -> list[EmailAttempt]:
        return list(
            self.db.scalars(
                select(EmailAttempt)
                .where(EmailAttempt.email_id == email_id)
                .order_by(EmailAttempt.attempt.asc(), EmailAttempt.id.asc())
            ).all()
        )

    def list_provider_health(self) -> list[EmailProviderHealth]:
        return list(
            self.db.scalars(
                select(EmailProviderHealth).order_by(EmailProviderHealth.provider)
            ).all()
        )

    def oldest_unsent_at(self) -> datetime | None:
        return self.db.scalar(
            select(func.min(EmailOutboxItem.created_at)).where(
                EmailOutboxItem.status.in_((*_READY, EmailStatus.SENDING))
            )
        )

    def count_unsent(self) -> int:
        return (
            self.db.scalar(
                select(func.count(EmailOutboxItem.id)).where(
                    EmailOutboxItem.status.in_((*_READY, EmailStatus.SENDING))
                )
            )
            or 0
        )

    def list_since(self, since: datetime) -> list[EmailOutboxItem]:
        """Itens criados desde ``since``, só os campos do painel."""
        return list(
            self.db.scalars(
                select(EmailOutboxItem)
                .options(
                    load_only(
                        EmailOutboxItem.status,
                        EmailOutboxItem.created_at,
                        EmailOutboxItem.sent_at,
                    )
                )
                .where(EmailOutboxItem.created_at >= since)
            ).all()
        )
