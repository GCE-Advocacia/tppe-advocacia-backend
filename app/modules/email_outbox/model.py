import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base_model import Base


class EmailStatus(str, Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    DEAD = "DEAD"
    CANCELLED = "CANCELLED"


class EmailOutboxItem(Base):
    """E-mail na fila de saída e, depois de enviado, no histórico.

    ``FAILED`` volta a ser tentado em ``next_attempt_at``; ``DEAD`` não.
    O ``context`` guarda o que o template precisa; links com token são
    apagados dele e mascarados no HTML quando o item chega ao fim.
    """

    __tablename__ = "email_outbox"
    __table_args__ = (
        Index("ix_email_outbox_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_email_outbox_related", "related_type", "related_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    template_id: Mapped[str] = mapped_column(String(100), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    to: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cc: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    bcc: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    html: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EmailStatus] = mapped_column(
        SAEnum(EmailStatus, name="emailstatus", native_enum=False, length=10),
        nullable=False,
        default=EmailStatus.PENDING,
        server_default=EmailStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    related_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
