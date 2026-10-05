from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal


from sqlalchemy import and_, delete, exists, select
from sqlalchemy.orm import Session, joinedload

from app.modules.clients.model import Client
from app.modules.payments.model import (
    Payment,
    PaymentReminder,
    PaymentStatus,
    ReminderKind,
    ReminderStatus,
)


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        client_id: int,
        payment_date: date,
        amount: Decimal | None = None,
        description: str | None = None,
        created_by: int | None = None,
        status: PaymentStatus = PaymentStatus.PENDING,
    ) -> Payment:
        payment = Payment(
            client_id=client_id,
            payment_date=payment_date,
            amount=amount,
            description=description,
            created_by=created_by,
            status=status,
        )

        self.db.add(payment)
        self.db.flush()

        return payment

    def get_by_id(self, payment_id: int) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id)

        return self.db.scalars(stmt).first()

    def list(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        status: PaymentStatus | None = None,
    ) -> list[Payment]:
        stmt = (
            select(Payment)
            .join(Client, Payment.client_id == Client.id)
            .where(Client.deleted_at.is_(None))
            .order_by(Payment.payment_date.asc())
        )

        if start_date is not None:
            stmt = stmt.where(Payment.payment_date >= start_date)

        if end_date is not None:
            stmt = stmt.where(Payment.payment_date <= end_date)

        if status is not None:
            stmt = stmt.where(Payment.status == status)

        return list(self.db.scalars(stmt).all())

    def update(
        self,
        payment: Payment,
        data: dict,
    ) -> Payment:
        for field, value in data.items():
            setattr(payment, field, value)

        self.db.flush()

        return payment

    def delete(self, payment: Payment) -> None:
        self.db.delete(payment)
        self.db.flush()


class PaymentReminderRepository:
    """Nunca comita: o Service que orquestra fecha a transação com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_due_for_reminder(
        self, today: date
    ) -> list[tuple[Payment, ReminderKind]]:
        """Pagamentos pendentes que vencem hoje ou amanhã e ainda não tiveram o
        lembrete daquele tipo enviado com sucesso."""
        due = self._due_on(today + timedelta(days=1), ReminderKind.D_MINUS_1)
        due += self._due_on(today, ReminderKind.D_ZERO)
        return due

    def _due_on(
        self, due_date: date, kind: ReminderKind
    ) -> list[tuple[Payment, ReminderKind]]:
        already_sent = exists().where(
            and_(
                PaymentReminder.payment_id == Payment.id,
                PaymentReminder.kind == kind,
                PaymentReminder.status == ReminderStatus.SENT,
            )
        )
        stmt = (
            select(Payment)
            .join(Client, Payment.client_id == Client.id)
            .options(joinedload(Payment.client))
            .where(
                Client.deleted_at.is_(None),
                Payment.status == PaymentStatus.PENDING,
                Payment.payment_date == due_date,
                ~already_sent,
            )
            .order_by(Payment.id.asc())
        )
        return [(payment, kind) for payment in self.db.scalars(stmt).all()]

    def get(self, payment_id: int, kind: ReminderKind) -> PaymentReminder | None:
        stmt = select(PaymentReminder).where(
            PaymentReminder.payment_id == payment_id,
            PaymentReminder.kind == kind,
        )
        return self.db.scalars(stmt).first()

    def register(
        self,
        payment_id: int,
        kind: ReminderKind,
        email: str | None,
        status: ReminderStatus,
        error_message: str | None = None,
    ) -> PaymentReminder:
        """Grava a tentativa. Se já existe registro (falha ou sem e-mail),
        atualiza o mesmo em vez de criar outro, respeitando a constraint única."""
        reminder = self.get(payment_id, kind)
        if reminder is None:
            reminder = PaymentReminder(payment_id=payment_id, kind=kind)
            self.db.add(reminder)

        reminder.email = email
        reminder.status = status
        reminder.error_message = error_message[:500] if error_message else None
        reminder.sent_at = datetime.now(timezone.utc)

        self.db.flush()
        return reminder

    def list(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        client_id: int | None = None,
        status: ReminderStatus | None = None,
        kind: ReminderKind | None = None,
    ) -> list[PaymentReminder]:
        stmt = (
            select(PaymentReminder)
            .join(Payment, PaymentReminder.payment_id == Payment.id)
            .options(
                joinedload(PaymentReminder.payment).joinedload(Payment.client)
            )
            .order_by(PaymentReminder.sent_at.desc(), PaymentReminder.id.desc())
        )

        if start_date is not None:
            start = datetime.combine(start_date, time.min, timezone.utc)
            stmt = stmt.where(PaymentReminder.sent_at >= start)

        if end_date is not None:
            end = datetime.combine(end_date + timedelta(days=1), time.min, timezone.utc)
            stmt = stmt.where(PaymentReminder.sent_at < end)

        if client_id is not None:
            stmt = stmt.where(Payment.client_id == client_id)

        if status is not None:
            stmt = stmt.where(PaymentReminder.status == status)

        if kind is not None:
            stmt = stmt.where(PaymentReminder.kind == kind)

        return list(self.db.scalars(stmt).unique().all())

    def list_by_payment(self, payment_id: int) -> list[PaymentReminder]:
        stmt = (
            select(PaymentReminder)
            .options(
                joinedload(PaymentReminder.payment).joinedload(Payment.client)
            )
            .where(PaymentReminder.payment_id == payment_id)
            .order_by(PaymentReminder.sent_at.asc(), PaymentReminder.id.asc())
        )
        return list(self.db.scalars(stmt).unique().all())

    def delete_by_payment(self, payment_id: int) -> None:
        self.db.execute(
            delete(PaymentReminder).where(PaymentReminder.payment_id == payment_id)
        )
        self.db.flush()
