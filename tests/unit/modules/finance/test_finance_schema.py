from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.finance.schema import FinancialTransactionCreate


def build(**kwargs) -> FinancialTransactionCreate:
    data = {
        "description": "Honorários contratuais",
        "amount": "1500.50",
        "transaction_date": date(2026, 9, 1),
    }
    data.update(kwargs)
    return FinancialTransactionCreate(**data)


class TestFinancialTransactionCreate:
    def test_accepts_valid_payload(self):
        payload = build()

        assert payload.amount == Decimal("1500.50")

    @pytest.mark.parametrize("amount", ["0", "-10.00"])
    def test_rejects_non_positive_amount(self, amount):
        with pytest.raises(ValidationError):
            build(amount=amount)

    def test_rejects_more_than_two_decimal_places(self):
        with pytest.raises(ValidationError):
            build(amount="10.005")

    def test_rejects_empty_description(self):
        with pytest.raises(ValidationError):
            build(description="")
