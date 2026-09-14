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


def _create(
    repo: FinancialTransactionRepository,
    type_: TransactionType,
    amount: str,
    day: date,
):
    return repo.create(
        type_=type_,
        description=f"{type_.value} {amount}",
        amount=Decimal(amount),
        transaction_date=day,
        created_by=None,
    )


class TestList:
    def test_orders_by_transaction_date_desc(self, db: Session):
        repo = FinancialTransactionRepository(db)
        older = _create(repo, TransactionType.INCOME, "100.00", date(2026, 9, 1))
        newer = _create(repo, TransactionType.EXPENSE, "50.00", date(2026, 9, 20))
        middle = _create(repo, TransactionType.INCOME, "70.00", date(2026, 9, 10))

        items, total = repo.list()

        assert total == 3
        assert [t.id for t in items] == [newer.id, middle.id, older.id]

    def test_paginates(self, db: Session):
        repo = FinancialTransactionRepository(db)
        for day in (1, 2, 3):
            _create(repo, TransactionType.INCOME, "10.00", date(2026, 9, day))

        items, total = repo.list(page=2, limit=2)

        assert total == 3
        assert len(items) == 1
