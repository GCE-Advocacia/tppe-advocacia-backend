from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.finance.model import TransactionType
from app.modules.finance.repository import FinancialTransactionRepository


class TestCreate:
    def test_persists_transaction(self, db: Session):
        repo = FinancialTransactionRepository(db)

        transaction = repo.create(
            type_=TransactionType.INCOME,
            description="Honorários contratuais",
            amount=Decimal("1500.50"),
            transaction_date=date(2026, 9, 1),
            created_by=None,
        )

        assert transaction.id is not None
        assert transaction.type == TransactionType.INCOME
        assert transaction.amount == Decimal("1500.50")
