from __future__ import annotations

from app.modules.finance.model import FinancialTransaction, TransactionType
from app.modules.finance.repository import FinancialTransactionRepository
from app.modules.finance.schema import FinancialTransactionCreate
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work


class FinanceService:
    def __init__(self, repository: FinancialTransactionRepository) -> None:
        self.repository = repository

    def create_income(
        self, payload: FinancialTransactionCreate, current_user: User
    ) -> FinancialTransaction:
        return self._create(TransactionType.INCOME, payload, current_user)

    def _create(
        self,
        type_: TransactionType,
        payload: FinancialTransactionCreate,
        current_user: User,
    ) -> FinancialTransaction:
        with unit_of_work(self.repository.db):
            transaction = self.repository.create(
                type_=type_,
                description=payload.description,
                amount=payload.amount,
                transaction_date=payload.transaction_date,
                created_by=current_user.id,
            )
        return transaction
