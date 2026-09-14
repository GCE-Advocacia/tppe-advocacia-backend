from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.finance.model import FinancialTransaction, TransactionType
from app.modules.finance.repository import FinancialTransactionRepository
from app.modules.finance.schema import (
    FinancialSummaryRead,
    FinancialTransactionCreate,
)
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import InvalidFinancialPeriodError


class FinanceService:
    def __init__(self, repository: FinancialTransactionRepository) -> None:
        self.repository = repository

    def create_income(
        self, payload: FinancialTransactionCreate, current_user: User
    ) -> FinancialTransaction:
        return self._create(TransactionType.INCOME, payload, current_user)

    def create_expense(
        self, payload: FinancialTransactionCreate, current_user: User
    ) -> FinancialTransaction:
        return self._create(TransactionType.EXPENSE, payload, current_user)

    def list_transactions(
        self,
        page: int,
        limit: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[FinancialTransaction], int]:
        self._validate_period(date_from, date_to)
        return self.repository.list(
            date_from=date_from, date_to=date_to, page=page, limit=limit
        )

    def get_total_income(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> Decimal:
        self._validate_period(date_from, date_to)
        return self.repository.sum_amount(
            TransactionType.INCOME, date_from=date_from, date_to=date_to
        )

    def get_total_expense(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> Decimal:
        self._validate_period(date_from, date_to)
        return self.repository.sum_amount(
            TransactionType.EXPENSE, date_from=date_from, date_to=date_to
        )

    @staticmethod
    def calculate_balance(total_income: Decimal, total_expense: Decimal) -> Decimal:
        return total_income - total_expense

    def get_balance(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> Decimal:
        return self.calculate_balance(
            self.get_total_income(date_from, date_to),
            self.get_total_expense(date_from, date_to),
        )

    def get_summary(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> FinancialSummaryRead:
        total_income = self.get_total_income(date_from, date_to)
        total_expense = self.get_total_expense(date_from, date_to)
        return FinancialSummaryRead(
            date_from=date_from,
            date_to=date_to,
            total_income=total_income,
            total_expense=total_expense,
            balance=self.calculate_balance(total_income, total_expense),
        )

    @staticmethod
    def _validate_period(date_from: date | None, date_to: date | None) -> None:
        if date_from is not None and date_to is not None and date_from > date_to:
            raise InvalidFinancialPeriodError()

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
