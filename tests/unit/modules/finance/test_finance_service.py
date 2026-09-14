from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.finance.model import TransactionType
from app.modules.finance.schema import FinancialTransactionCreate
from app.modules.finance.service import FinanceService


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
