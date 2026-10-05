from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.clients.model import Client
from app.modules.users.model import User
from app.shared.db.base_model import Base


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"


class ReminderKind(str, Enum):
    D_MINUS_1 = "D_MINUS_1"
    D_ZERO = "D_ZERO"


class ReminderStatus(str, Enum):
    SENT = "SENT"
    FAILED = "FAILED"
    NO_EMAIL = "NO_EMAIL"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    payment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="paymentstatus", native_enum=False, length=10),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
        index=True,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            use_alter=True,
            name="fk_payments_created_by",
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    client: Mapped[Client] = relationship(
        "Client",
        foreign_keys=[client_id],
    )

    creator: Mapped[User] = relationship(
        "User",
        foreign_keys=[created_by],
    )


class PaymentReminder(Base):
    """Lembrete de vencimento por pagamento e tipo (D-1 ou dia). A constraint
    única garante que cada tipo exista uma vez só por pagamento."""

    __tablename__ = "payment_reminders"
    __table_args__ = (
        UniqueConstraint(
            "payment_id", "kind", name="uq_payment_reminders_payment_kind"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[ReminderKind] = mapped_column(
        SAEnum(ReminderKind, name="reminderkind", native_enum=False, length=10),
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(ReminderStatus, name="reminderstatus", native_enum=False, length=10),
        nullable=False,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    payment: Mapped[Payment] = relationship(
        "Payment",
        foreign_keys=[payment_id],
    )

    @property
    def client_id(self) -> int:
        return self.payment.client_id

    @property
    def client_name(self) -> str:
        return self.payment.client.name

    @property
    def payment_date(self) -> date:
        return self.payment.payment_date

    @property
    def amount(self) -> Decimal | None:
        return self.payment.amount
