import calendar
import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.service import EmailOutbox
from app.modules.payments.model import PaymentStatus, ReminderKind, ReminderStatus
from app.modules.payments.repository import (
    PaymentReminderRepository,
    PaymentRepository,
)
from app.modules.payments.schema import PaymentCreate, PaymentUpdate
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work

logger = logging.getLogger(__name__)

REMINDER_TEMPLATES = {
    ReminderKind.D_MINUS_5: "payment_reminder_d5",
    ReminderKind.D_MINUS_1: "payment_reminder_d1",
    ReminderKind.D_ZERO: "payment_reminder_d0",
}
PAYMENT_RELATED_TYPE = "payment"


def add_months(start: date, months: int) -> date:
    """Mesmo dia ``months`` meses depois; dia 31 vira o último dia do mês."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.payment_repository = PaymentRepository(db)
        self.client_repository = ClientRepository(db)
        self.reminder_repository = PaymentReminderRepository(db)
        self.outbox = EmailOutbox(EmailOutboxRepository(db))

    def create(
        self,
        payload: PaymentCreate,
        current_user: User,
    ):
        client = self.client_repository.get_by_id(
            payload.client_id
        )

        if client is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente não encontrado.",
            )

        # Recorrente: um vencimento por mês, no mesmo dia, todos de uma vez.
        installments = payload.recurrence_months or 1
        recurrence_id = str(uuid.uuid4()) if installments > 1 else None

        with unit_of_work(self.payment_repository.db):
            payments = [
                self.payment_repository.create(
                    client_id=payload.client_id,
                    payment_date=add_months(payload.payment_date, index),
                    amount=payload.amount,
                    description=payload.description,
                    created_by=current_user.id,
                    status=payload.status if index == 0 else PaymentStatus.PENDING,
                    recurrence_id=recurrence_id,
                    installment=index + 1 if recurrence_id else None,
                    installments=installments if recurrence_id else None,
                )
                for index in range(installments)
            ]

        return payments[0]

    def get_by_id(self, payment_id: int):
        payment = self.payment_repository.get_by_id(
            payment_id
        )

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pagamento não encontrado.",
            )

        return payment

    def list(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        payment_status: PaymentStatus | None = None,
    ):
        self._validate_period(start_date, end_date)

        return self.payment_repository.list(
            start_date=start_date,
            end_date=end_date,
            status=payment_status,
        )

    def update(
        self,
        payment_id: int,
        payload: PaymentUpdate,
    ):
        payment = self.get_by_id(payment_id)

        data = payload.model_dump(
            exclude_unset=True
        )

        if not data:
            return payment

        if "client_id" in data:
            client = self.client_repository.get_by_id(
                data["client_id"]
            )

            if client is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente não encontrado.",
                )

        # Vencimento novo pede lembretes novos.
        due_date_changed = (
            "payment_date" in data
            and data["payment_date"] != payment.payment_date
        )

        with unit_of_work(self.payment_repository.db):
            if due_date_changed:
                self.reminder_repository.delete_by_payment(payment.id)
                self.outbox.cancel_related(PAYMENT_RELATED_TYPE, payment.id)

            payment = self.payment_repository.update(
                payment,
                data,
            )

        return payment

    def delete(self, payment_id: int) -> None:
        payment = self.get_by_id(payment_id)

        with unit_of_work(self.payment_repository.db):
            self.outbox.cancel_related(PAYMENT_RELATED_TYPE, payment.id)
            self.payment_repository.delete(payment)

    def list_reminders(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        client_id: int | None = None,
        reminder_status: ReminderStatus | None = None,
        kind: ReminderKind | None = None,
    ):
        self._validate_period(start_date, end_date)

        return self.reminder_repository.list(
            start_date=start_date,
            end_date=end_date,
            client_id=client_id,
            status=reminder_status,
            kind=kind,
        )

    def list_payment_reminders(self, payment_id: int):
        self.get_by_id(payment_id)

        return self.reminder_repository.list_by_payment(payment_id)

    @staticmethod
    def _validate_period(
        start_date: date | None,
        end_date: date | None,
    ) -> None:
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A data inicial não pode ser maior "
                    "que a data final."
                ),
            )

class PaymentReminderService:
    def __init__(self, db: Session, outbox: EmailOutbox | None = None) -> None:
        self.db = db
        self.reminder_repo = PaymentReminderRepository(db)
        self.outbox = outbox or EmailOutbox(EmailOutboxRepository(db))

    def dispatch(self, today: date) -> dict[str, int]:
        """Põe na fila os lembretes do dia. Lembrete e e-mail entram na mesma
        transação; quem envia é o worker da fila, que atualiza o lembrete."""
        due_reminders = self.reminder_repo.list_due_for_reminder(today)
        results = {"queued": 0, "no_email": 0}

        for payment, kind in due_reminders:
            email = payment.client.email
            with unit_of_work(self.db):
                # Regra: cliente sem e-mail não recebe disparo.
                if not email:
                    self.reminder_repo.register(
                        payment_id=payment.id,
                        kind=kind,
                        email=None,
                        status=ReminderStatus.NO_EMAIL,
                    )
                    results["no_email"] += 1
                    continue

                item = self.outbox.enqueue(
                    REMINDER_TEMPLATES[kind],
                    self._email_context(payment, today),
                    to=email,
                    related=(PAYMENT_RELATED_TYPE, payment.id),
                )
                self.reminder_repo.register(
                    payment_id=payment.id,
                    kind=kind,
                    email=email,
                    status=ReminderStatus.QUEUED,
                    email_outbox_id=item.id,
                )
            results["queued"] += 1

        return results

    def sync_from_email(self, item: EmailOutboxItem) -> None:
        """Ouvinte do worker: o lembrete acompanha o fim do e-mail na fila."""
        if item.related_type != PAYMENT_RELATED_TYPE:
            return
        self.reminder_repo.sync_from_email(
            item.id,
            sent=item.status == EmailStatus.SENT,
            error=item.last_error
            if item.status != EmailStatus.CANCELLED
            else "E-mail cancelado",
            finished_at=item.sent_at or datetime.now(timezone.utc),
        )

    @staticmethod
    def _email_context(payment, today: date) -> dict:
        """Contexto em tipos de JSON (vai para a fila de e-mail como está)."""
        return {
            "client_name": payment.client.name,
            "description": payment.description,
            "amount": str(payment.amount) if payment.amount is not None else None,
            "due_date": payment.payment_date.isoformat(),
            "days_left": (payment.payment_date - today).days,
        }
