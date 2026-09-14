from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.finance.model import TransactionType
from app.modules.finance.schema import FinancialTransactionCreate
from app.modules.finance.service import FinanceService
from app.shared.exceptions import InvalidFinancialPeriodError


def make_payload(**kwargs) -> FinancialTransactionCreate:
    data = {
        "description": "Honorários contratuais",
        "amount": Decimal("1500.50"),
        "transaction_date": date(2026, 9, 1),
    }
    data.update(kwargs)
    return FinancialTransactionCreate(**data)


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return FinanceService(repository=repo)


@pytest.fixture
def admin():
    return SimpleNamespace(id=7)


class TestCreateIncome:
    def test_creates_transaction_with_income_type(self, service, repo, admin):
        created = SimpleNamespace(id=1)
        repo.create.return_value = created

        result = service.create_income(make_payload(), admin)

        assert result is created
        kwargs = repo.create.call_args.kwargs
        assert kwargs["type_"] == TransactionType.INCOME
        assert kwargs["amount"] == Decimal("1500.50")
        assert kwargs["transaction_date"] == date(2026, 9, 1)
        assert kwargs["created_by"] == 7

    def test_commits_transaction(self, service, repo, admin):
        service.create_income(make_payload(), admin)

        repo.db.commit.assert_called_once()


class TestCreateExpense:
    def test_creates_transaction_with_expense_type(self, service, repo, admin):
        created = SimpleNamespace(id=2)
        repo.create.return_value = created

        result = service.create_expense(
            make_payload(description="Aluguel", amount=Decimal("3200.00")), admin
        )

        assert result is created
        kwargs = repo.create.call_args.kwargs
        assert kwargs["type_"] == TransactionType.EXPENSE
        assert kwargs["amount"] == Decimal("3200.00")
        assert kwargs["created_by"] == 7


class TestListTransactions:
    def test_delegates_pagination_to_repository(self, service, repo):
        repo.list.return_value = ([], 0)

        items, total = service.list_transactions(page=2, limit=10)

        assert (items, total) == ([], 0)
        kwargs = repo.list.call_args.kwargs
        assert kwargs["page"] == 2
        assert kwargs["limit"] == 10


class TestListTransactionsByPeriod:
    def test_passes_period_to_repository(self, service, repo):
        repo.list.return_value = ([], 0)

        service.list_transactions(
            page=1, limit=20, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)
        )

        kwargs = repo.list.call_args.kwargs
        assert kwargs["date_from"] == date(2026, 9, 1)
        assert kwargs["date_to"] == date(2026, 9, 30)

    def test_raises_when_date_from_after_date_to(self, service, repo):
        with pytest.raises(InvalidFinancialPeriodError):
            service.list_transactions(
                page=1, limit=20, date_from=date(2026, 9, 30), date_to=date(2026, 9, 1)
            )

        repo.list.assert_not_called()

    def test_accepts_single_day_period(self, service, repo):
        repo.list.return_value = ([], 0)

        service.list_transactions(
            page=1, limit=20, date_from=date(2026, 9, 1), date_to=date(2026, 9, 1)
        )

        repo.list.assert_called_once()


class TestGetTotalIncome:
    def test_sums_income_type_for_period(self, service, repo):
        repo.sum_amount.return_value = Decimal("1500.00")

        total = service.get_total_income(date(2026, 9, 1), date(2026, 9, 30))

        assert total == Decimal("1500.00")
        repo.sum_amount.assert_called_once_with(
            TransactionType.INCOME,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 30),
        )

    def test_raises_on_inverted_period(self, service, repo):
        with pytest.raises(InvalidFinancialPeriodError):
            service.get_total_income(date(2026, 9, 30), date(2026, 9, 1))

        repo.sum_amount.assert_not_called()
