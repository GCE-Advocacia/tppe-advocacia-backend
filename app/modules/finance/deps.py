from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.modules.finance.repository import FinancialTransactionRepository
from app.modules.finance.service import FinanceService


def get_finance_service(db: Session = Depends(get_db)) -> FinanceService:
    return FinanceService(FinancialTransactionRepository(db))
