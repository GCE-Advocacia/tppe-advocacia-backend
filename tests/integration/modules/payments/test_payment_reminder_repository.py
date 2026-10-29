from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.payments.model import (
    PaymentReminder,
    PaymentStatus,
    ReminderKind,
    ReminderStatus,
)
from app.modules.payments.repository import (
    PaymentReminderRepository,
    PaymentRepository,
)
from app.modules.users.repository import UserRepository
from app.shared.types import Role

TODAY = date(2026, 10, 10)
TOMORROW = date(2026, 10, 11)


@pytest.fixture
def user_id(db: Session) -> int:
    user = UserRepository(db).create(
        name="Admin", email="admin@test.com", hashed_password="h", role=Role.ADMIN
    )
    return user.id


@pytest.fixture
def client_id(db: Session) -> int:
    return ClientRepository(db).create(name="Maria", email="maria@test.com").id


def make_payment(
    db: Session,
    client_id: int,
    user_id: int,
    payment_date: date,
    status: PaymentStatus = PaymentStatus.PENDING,
):
    return PaymentRepository(db).create(
        client_id=client_id,
        payment_date=payment_date,
        amount=Decimal("150.00"),
        description="Honorários",
        created_by=user_id,
        status=status,
    )


class TestListDueForReminder:
    def test_returns_d_minus_1_for_tomorrow_and_d_zero_for_today(
        self, db: Session, client_id: int, user_id: int
    ):
        due_tomorrow = make_payment(db, client_id, user_id, TOMORROW)
        due_today = make_payment(db, client_id, user_id, TODAY)

        result = PaymentReminderRepository(db).list_due_for_reminder(TODAY)

        assert (due_tomorrow, ReminderKind.D_MINUS_1) in result
        assert (due_today, ReminderKind.D_ZERO) in result
        assert len(result) == 2

    def test_ignores_payments_outside_window(
        self, db: Session, client_id: int, user_id: int
    ):
        make_payment(db, client_id, user_id, date(2026, 10, 12))
        make_payment(db, client_id, user_id, date(2026, 10, 9))

        assert PaymentReminderRepository(db).list_due_for_reminder(TODAY) == []

    def test_ignores_paid_payments(self, db: Session, client_id: int, user_id: int):
        make_payment(db, client_id, user_id, TODAY, status=PaymentStatus.PAID)

        assert PaymentReminderRepository(db).list_due_for_reminder(TODAY) == []

    def test_ignores_deleted_clients(self, db: Session, client_id: int, user_id: int):
        make_payment(db, client_id, user_id, TODAY)
        client = ClientRepository(db).get_by_id(client_id)
        client.deleted_at = datetime.now(timezone.utc)
        db.flush()

        assert PaymentReminderRepository(db).list_due_for_reminder(TODAY) == []

    def test_skips_kind_already_sent(self, db: Session, client_id: int, user_id: int):
        payment = make_payment(db, client_id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        repo.register(
            payment.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )

        assert repo.list_due_for_reminder(TODAY) == []

    def test_d_minus_1_sent_does_not_block_d_zero(
        self, db: Session, client_id: int, user_id: int
    ):
        payment = make_payment(db, client_id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        repo.register(
            payment.id, ReminderKind.D_MINUS_1, "maria@test.com", ReminderStatus.SENT
        )

        assert repo.list_due_for_reminder(TODAY) == [(payment, ReminderKind.D_ZERO)]

    @pytest.mark.parametrize(
        "reminder_status", [ReminderStatus.FAILED, ReminderStatus.NO_EMAIL]
    )
    def test_retries_when_previous_attempt_was_not_sent(
        self, db: Session, client_id: int, user_id: int, reminder_status
    ):
        payment = make_payment(db, client_id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        repo.register(payment.id, ReminderKind.D_ZERO, None, reminder_status)

        assert repo.list_due_for_reminder(TODAY) == [(payment, ReminderKind.D_ZERO)]


class TestRegister:
    def test_persists_reminder(self, db: Session, client_id: int, user_id: int):
        payment = make_payment(db, client_id, user_id, TODAY)

        reminder = PaymentReminderRepository(db).register(
            payment.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )

        assert reminder.id is not None
        assert reminder.email == "maria@test.com"
        assert reminder.status == ReminderStatus.SENT
        assert reminder.sent_at is not None

    def test_updates_existing_row_instead_of_duplicating(
        self, db: Session, client_id: int, user_id: int
    ):
        payment = make_payment(db, client_id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        first = repo.register(
            payment.id,
            ReminderKind.D_ZERO,
            "maria@test.com",
            ReminderStatus.FAILED,
            error_message="timeout",
        )

        second = repo.register(
            payment.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )

        assert second.id == first.id
        assert second.status == ReminderStatus.SENT
        assert second.error_message is None
        assert len(repo.list_by_payment(payment.id)) == 1

    def test_truncates_long_error_message(
        self, db: Session, client_id: int, user_id: int
    ):
        payment = make_payment(db, client_id, user_id, TODAY)

        reminder = PaymentReminderRepository(db).register(
            payment.id,
            ReminderKind.D_ZERO,
            "maria@test.com",
            ReminderStatus.FAILED,
            error_message="x" * 800,
        )

        assert len(reminder.error_message) == 500

    def test_unique_constraint_blocks_duplicate_kind(
        self, db: Session, client_id: int, user_id: int
    ):
        payment = make_payment(db, client_id, user_id, TODAY)
        for _ in range(2):
            db.add(
                PaymentReminder(
                    payment_id=payment.id,
                    kind=ReminderKind.D_ZERO,
                    email="maria@test.com",
                    status=ReminderStatus.SENT,
                )
            )

        with pytest.raises(IntegrityError):
            db.flush()


class TestList:
    def test_exposes_client_and_payment_data(
        self, db: Session, client_id: int, user_id: int
    ):
        payment = make_payment(db, client_id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        repo.register(
            payment.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )

        [reminder] = repo.list()

        assert reminder.client_id == client_id
        assert reminder.client_name == "Maria"
        assert reminder.payment_date == TODAY
        assert reminder.amount == Decimal("150.00")

    def test_filters_by_status_kind_and_client(
        self, db: Session, client_id: int, user_id: int
    ):
        other_client = ClientRepository(db).create(name="João", email=None)
        payment = make_payment(db, client_id, user_id, TODAY)
        other_payment = make_payment(db, other_client.id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        repo.register(
            payment.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )
        repo.register(
            payment.id, ReminderKind.D_MINUS_1, "maria@test.com", ReminderStatus.SENT
        )
        repo.register(
            other_payment.id, ReminderKind.D_ZERO, None, ReminderStatus.NO_EMAIL
        )

        assert len(repo.list(status=ReminderStatus.NO_EMAIL)) == 1
        assert len(repo.list(kind=ReminderKind.D_MINUS_1)) == 1
        assert len(repo.list(client_id=client_id)) == 2

    def test_filters_by_sent_period(self, db: Session, client_id: int, user_id: int):
        payment = make_payment(db, client_id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        reminder = repo.register(
            payment.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )
        reminder.sent_at = datetime(2026, 10, 10, 11, 0, tzinfo=timezone.utc)
        db.flush()

        assert len(repo.list(start_date=TODAY, end_date=TODAY)) == 1
        assert repo.list(start_date=TOMORROW) == []
        assert repo.list(end_date=date(2026, 10, 9)) == []


class TestDeleteByPayment:
    def test_removes_only_that_payment_reminders(
        self, db: Session, client_id: int, user_id: int
    ):
        payment = make_payment(db, client_id, user_id, TODAY)
        other = make_payment(db, client_id, user_id, TODAY)
        repo = PaymentReminderRepository(db)
        repo.register(
            payment.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )
        repo.register(
            other.id, ReminderKind.D_ZERO, "maria@test.com", ReminderStatus.SENT
        )

        repo.delete_by_payment(payment.id)

        assert repo.list_by_payment(payment.id) == []
        assert len(repo.list_by_payment(other.id)) == 1
