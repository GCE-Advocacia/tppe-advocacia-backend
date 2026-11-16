from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus
from app.modules.payments.model import Payment, PaymentStatus
from app.modules.payments.schema import PaymentCreate, PaymentUpdate
from app.modules.payments.service import (
    PaymentReminderService,
    PaymentService,
    add_months,
)
from app.modules.users.repository import UserRepository
from app.shared.types import Role


@pytest.fixture
def admin(db: Session):
    user = UserRepository(db).create(
        name="Admin", email="admin@test.com", hashed_password="h", role=Role.ADMIN
    )
    db.commit()
    return user


@pytest.fixture
def client_id(db: Session) -> int:
    client = ClientRepository(db).create(name="Maria", email="maria@test.com")
    db.commit()
    return client.id


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 10, 28), 1, date(2026, 11, 28)),
        (date(2026, 10, 28), 3, date(2027, 1, 28)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 8, 31), 1, date(2026, 9, 30)),
    ],
)
def test_add_months_keeps_day_or_uses_last_day(start, months, expected):
    assert add_months(start, months) == expected


class TestRecurringPayment:
    def test_creates_one_payment_per_month(self, db, admin, client_id):
        first = PaymentService(db).create(
            PaymentCreate(
                client_id=client_id,
                payment_date=date(2026, 10, 28),
                amount=Decimal("500.00"),
                description="Honorários",
                recurrence_months=10,
            ),
            admin,
        )

        payments = db.query(Payment).order_by(Payment.payment_date).all()
        assert len(payments) == 10
        assert payments[0].id == first.id
        assert payments[1].payment_date == date(2026, 11, 28)
        assert payments[-1].payment_date == date(2027, 7, 28)
        assert {p.recurrence_id for p in payments} == {first.recurrence_id}
        assert [p.installment for p in payments] == list(range(1, 11))
        assert all(p.installments == 10 for p in payments)
        assert all(p.amount == Decimal("500.00") for p in payments)

    def test_only_first_keeps_paid_status(self, db, admin, client_id):
        PaymentService(db).create(
            PaymentCreate(
                client_id=client_id,
                payment_date=date(2026, 10, 28),
                status=PaymentStatus.PAID,
                recurrence_months=3,
            ),
            admin,
        )

        statuses = [p.status for p in db.query(Payment).order_by(Payment.payment_date)]
        assert statuses == [
            PaymentStatus.PAID,
            PaymentStatus.PENDING,
            PaymentStatus.PENDING,
        ]

    def test_without_recurrence_creates_single_payment(self, db, admin, client_id):
        payment = PaymentService(db).create(
            PaymentCreate(client_id=client_id, payment_date=date(2026, 10, 28)),
            admin,
        )

        assert db.query(Payment).count() == 1
        assert payment.recurrence_id is None
        assert payment.installment is None

    def test_limit_of_60_months(self, client_id):
        with pytest.raises(ValueError):
            PaymentCreate(
                client_id=client_id,
                payment_date=date(2026, 10, 28),
                recurrence_months=61,
            )


class TestQueuedReminderFollowsPayment:
    def test_changing_due_date_cancels_queued_email(self, db, admin, client_id):
        service = PaymentService(db)
        payment = service.create(
            PaymentCreate(client_id=client_id, payment_date=date(2026, 10, 10)), admin
        )
        PaymentReminderService(db).dispatch(date(2026, 10, 10))

        service.update(payment.id, PaymentUpdate(payment_date=date(2026, 11, 10)))

        item = db.query(EmailOutboxItem).one()
        assert item.status == EmailStatus.CANCELLED

    def test_deleting_payment_cancels_queued_email(self, db, admin, client_id):
        service = PaymentService(db)
        payment = service.create(
            PaymentCreate(client_id=client_id, payment_date=date(2026, 10, 10)), admin
        )
        PaymentReminderService(db).dispatch(date(2026, 10, 10))

        service.delete(payment.id)

        assert db.query(EmailOutboxItem).one().status == EmailStatus.CANCELLED
