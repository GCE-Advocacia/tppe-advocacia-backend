from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.finance.model import FinancialTransaction, TransactionType


class FinancialTransactionRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        type_: TransactionType,
        description: str,
        amount: Decimal,
        transaction_date: date,
        created_by: int | None,
    ) -> FinancialTransaction:
        transaction = FinancialTransaction(
            type=type_,
            description=description,
            amount=amount,
            transaction_date=transaction_date,
            created_by=created_by,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction

    @staticmethod
    def _apply_period(
        stmt: Select, date_from: date | None, date_to: date | None
    ) -> Select:
        if date_from is not None:
            stmt = stmt.where(FinancialTransaction.transaction_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(FinancialTransaction.transaction_date <= date_to)
        return stmt

    def list(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[FinancialTransaction], int]:
        base = self._apply_period(select(FinancialTransaction), date_from, date_to)

        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        items = list(
            self.db.scalars(
                base.order_by(
                    FinancialTransaction.transaction_date.desc(),
                    FinancialTransaction.id.desc(),
                )
                .offset((page - 1) * limit)
                .limit(limit)
            ).all()
        )
        return items, total

    def sum_amount(
        self,
        type_: TransactionType,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Decimal:
        stmt = self._apply_period(
            select(func.coalesce(func.sum(FinancialTransaction.amount), 0)).where(
                FinancialTransaction.type == type_
            ),
            date_from,
            date_to,
        )
        total = self.db.scalar(stmt)
        return Decimal(str(total)).quantize(Decimal("0.01"))
