from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schema import PaymentCreate, PaymentUpdate
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.payment_repository = PaymentRepository(db)
        self.client_repository = ClientRepository(db)

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
    ):
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A data inicial não pode ser maior "
                    "que a data final."
                ),
            )

        return self.payment_repository.list(
            start_date=start_date,
            end_date=end_date,
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

        with unit_of_work(self.payment_repository.db):
            payment = self.payment_repository.update(
                payment,
                data,
            )

        return payment

    def delete(self, payment_id: int) -> None:
        payment = self.get_by_id(payment_id)

        with unit_of_work(self.payment_repository.db):
            self.payment_repository.delete(payment)