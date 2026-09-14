from __future__ import annotations

from datetime import date
from decimal import Decimal

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
