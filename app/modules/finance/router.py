from fastapi import APIRouter, Depends, status

from app.modules.finance.deps import get_finance_service
from app.modules.finance.schema import (
    FinancialTransactionCreate,
    FinancialTransactionRead,
)
from app.modules.finance.service import FinanceService
from app.modules.users.model import User
from app.shared.deps.auth import require_admin
from app.shared.http.responses import SuccessResponse, error_responses, ok

router = APIRouter(prefix="/finance", tags=["Finance"])


@router.post(
    "/incomes",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[FinancialTransactionRead],
    responses=error_responses(401, 403, 422),
    summary="Registra uma entrada financeira (admin)",
)
def create_income(
    payload: FinancialTransactionCreate,
    service: FinanceService = Depends(get_finance_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[FinancialTransactionRead]:
    transaction = service.create_income(payload, current_user)
    return ok(FinancialTransactionRead.model_validate(transaction))


@router.post(
    "/expenses",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[FinancialTransactionRead],
    responses=error_responses(401, 403, 422),
    summary="Registra uma saída financeira (admin)",
)
def create_expense(
    payload: FinancialTransactionCreate,
    service: FinanceService = Depends(get_finance_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[FinancialTransactionRead]:
    transaction = service.create_expense(payload, current_user)
    return ok(FinancialTransactionRead.model_validate(transaction))
