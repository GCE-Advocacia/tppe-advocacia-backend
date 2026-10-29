import logging
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.payments.model import PaymentStatus, ReminderKind, ReminderStatus
from app.modules.payments.repository import (
    PaymentReminderRepository,
    PaymentRepository,
)
from app.modules.payments.schema import PaymentCreate, PaymentUpdate
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.payment_repository = PaymentRepository(db)
        self.client_repository = ClientRepository(db)
        self.reminder_repository = PaymentReminderRepository(db)

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

        with unit_of_work(self.payment_repository.db):
            payment = self.payment_repository.create(
                client_id=payload.client_id,
                payment_date=payload.payment_date,
                amount=payload.amount,
                description=payload.description,
                created_by=current_user.id,
                status=payload.status,
            )

        return payment

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

            payment = self.payment_repository.update(
                payment,
                data,
            )

        return payment

    def delete(self, payment_id: int) -> None:
        payment = self.get_by_id(payment_id)

        with unit_of_work(self.payment_repository.db):
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
    def __init__(self, db: Session, email_service) -> None:
        self.db = db
        self.reminder_repo = PaymentReminderRepository(db)
        self.email_service = email_service

    def dispatch(self, today: date) -> dict:
        """Busca pagamentos próximos ao vencimento e dispara os e-mails."""
        due_reminders = self.reminder_repo.list_due_for_reminder(today)
        results = {"sent": 0, "failed": 0, "no_email": 0}

        for payment, kind in due_reminders:
            email = payment.client.email
            
            # Regra: Cliente sem e-mail não recebe disparo
            if not email:
                with unit_of_work(self.db):
                    self.reminder_repo.register(
                        payment_id=payment.id,
                        kind=kind,
                        email=None,
                        status=ReminderStatus.NO_EMAIL
                    )
                results["no_email"] += 1
                continue
                
            subject, body = self._build_email_content(payment, kind)
            
            try:
                # Tenta disparar o e-mail usando o serviço injetado (Resend ou Fake)
                self.email_service.send(
                    to=email,
                    subject=subject,
                    html=body
                )
                status = ReminderStatus.SENT
                error_msg = None
                results["sent"] += 1
            except Exception as e:
                logger.error(f"Falha ao enviar lembrete do pagamento {payment.id} para {email}: {e}")
                status = ReminderStatus.FAILED
                error_msg = str(e)
                results["failed"] += 1
                
            # Regra: Grava o registro da tentativa logo após a ação, 
            # garantindo que o `unit_of_work` feche a transação por iteração.
            with unit_of_work(self.db):
                self.reminder_repo.register(
                    payment_id=payment.id,
                    kind=kind,
                    email=email,
                    status=status,
                    error_message=error_msg
                )
                
        return results

    def _build_email_content(self, payment, kind: ReminderKind) -> tuple[str, str]:
        """Constrói o template do e-mail diferenciando véspera (D-1) e dia do vencimento (D-0)."""
        client_name = payment.client.name
        
      
        if payment.amount is not None:
            amount_str = f"R$ {payment.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            amount_str = "Valor a consultar"
            
        date_str = payment.payment_date.strftime("%d/%m/%Y")
        desc = payment.description or "Serviços jurídicos / Honorários"
        
        if kind == ReminderKind.D_MINUS_1:
            subject = "Lembrete: Vencimento amanhã"
            body = (
                f"Olá, {client_name}.\n\n"
                f"Este é um lembrete de que o pagamento referente a '{desc}' "
                f"no valor de {amount_str} vence amanhã, dia {date_str}.\n\n"
                "Por favor, desconsidere este aviso caso já tenha efetuado o pagamento."
            )
        else:
            subject = "Aviso: Vencimento hoje"
            body = (
                f"Olá, {client_name}.\n\n"
                f"Informamos que o pagamento referente a '{desc}' "
                f"no valor de {amount_str} vence hoje, dia {date_str}.\n\n"
                "Agradecemos a atenção e solicitamos que desconsidere caso já tenha pago."
            )
            
        return subject, body