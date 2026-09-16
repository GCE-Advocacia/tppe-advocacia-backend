from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    client_id: int
    payment_date: date
    amount: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=5000)


class PaymentUpdate(BaseModel):
    client_id: int | None = None
    payment_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=5000)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    payment_date: date
    amount: Decimal | None
    description: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime