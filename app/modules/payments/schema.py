from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.payments.model import PaymentStatus, ReminderKind, ReminderStatus


class PaymentCreate(BaseModel):
    client_id: int
    payment_date: date
    amount: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=5000)
    status: PaymentStatus = PaymentStatus.PENDING


class PaymentUpdate(BaseModel):
    client_id: int | None = None
    payment_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=5000)
    status: PaymentStatus | None = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    payment_date: date
    amount: Decimal | None
    description: str | None
    status: PaymentStatus
    created_by: int
    created_at: datetime
    updated_at: datetime


class PaymentReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_id: int
    client_id: int
    client_name: str
    payment_date: date
    amount: Decimal | None
    kind: ReminderKind
    email: str | None
    status: ReminderStatus
    error_message: str | None
    sent_at: datetime
