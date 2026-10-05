from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.finance.model import FinancialTransaction, TransactionType


class TestFinancialTransactionModel:
    def test_persists_income_with_two_decimal_places(self, db: Session):
        db.add(
            FinancialTransaction(
                type=TransactionType.INCOME,
                description="Honorários contratuais",
                amount=Decimal("1500.50"),
                transaction_date=date(2026, 9, 1),
            )
        )
        db.commit()
        db.expire_all()

        saved = db.scalars(select(FinancialTransaction)).one()

        assert saved.id is not None
        assert saved.type == TransactionType.INCOME
        assert saved.amount == Decimal("1500.50")
        assert saved.transaction_date == date(2026, 9, 1)

    def test_persists_expense_with_timestamps(self, db: Session):
        db.add(
            FinancialTransaction(
                type=TransactionType.EXPENSE,
                description="Aluguel do escritório",
                amount=Decimal("3200.00"),
                transaction_date=date(2026, 9, 5),
            )
        )
        db.commit()
        db.expire_all()

        saved = db.scalars(select(FinancialTransaction)).one()

        assert saved.type == TransactionType.EXPENSE
        assert saved.created_at is not None
        assert saved.updated_at is not None
