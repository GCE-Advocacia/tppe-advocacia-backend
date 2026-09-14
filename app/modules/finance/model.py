from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.users.model import User  # noqa: F401  registra "users" no metadata
from app.shared.db.base_model import Base


class TransactionType(str, Enum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    __table_args__ = (
        Index("ix_financial_transactions_transaction_date", "transaction_date"),
        Index("ix_financial_transactions_type", "type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, native_enum=False, length=10),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id", use_alter=True, name="fk_financial_transactions_created_by"
        ),
        nullable=True,
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
