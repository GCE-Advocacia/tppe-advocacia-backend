from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.finance.model import TransactionType


class FinancialTransactionCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    transaction_date: date


class FinancialTransactionRead(BaseModel):
    id: int
    type: TransactionType
    description: str
    amount: Decimal
    transaction_date: date
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinancialSummaryRead(BaseModel):
    date_from: date | None
    date_to: date | None
    total_income: Decimal
    total_expense: Decimal
    balance: Decimal
