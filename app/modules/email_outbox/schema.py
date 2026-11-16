from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.email_outbox.model import BreakerState, EmailStatus


class EmailLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    template_id: str
    template_name: str
    to: list[str]
    subject: str | None
    status: EmailStatus
    attempts: int
    provider: str | None
    last_error: str | None
    related_type: str | None
    related_id: int | None
    resent_from_id: str | None
    resendable: bool
    created_at: datetime
    next_attempt_at: datetime
    sent_at: datetime | None


class EmailAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt: int
    provider: str | None
    success: bool
    error: str | None
    duration_ms: int | None
    created_at: datetime


class EmailLogDetail(EmailLogRead):
    cc: list[str]
    bcc: list[str]
    html: str | None
    text: str | None
    timeline: list[EmailAttemptRead]


class EmailTypeRead(BaseModel):
    id: str
    name: str


class ResendBatchRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=200)


class ResendBatchSkipped(BaseModel):
    id: str
    reason: str


class ResendBatchResult(BaseModel):
    resent: list[str]
    skipped: list[ResendBatchSkipped]


class ProviderHealthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    state: BreakerState
    consecutive_failures: int
    opened_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None


class DailyCount(BaseModel):
    day: date
    sent: int
    failed: int
    dead: int


class EmailAlertRead(BaseModel):
    kind: str
    level: Literal["warning", "critical"]
    message: str


class EmailHealthRead(BaseModel):
    providers: list[ProviderHealthRead]
    queue_pending: int
    oldest_pending_at: datetime | None
    success_rate_24h: float | None
    avg_delivery_seconds_24h: float | None
    sent_24h: int
    dead_24h: int
    daily: list[DailyCount]
    alerts: list[EmailAlertRead]
