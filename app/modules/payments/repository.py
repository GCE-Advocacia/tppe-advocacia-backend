from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.clients.model import Client
from app.modules.payments.model import Payment


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
    ) -> Payment:
        payment = Payment(
            client_id=client_id,
            payment_date=payment_date,
            amount=amount,
            description=description,
            created_by=created_by,
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