from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.modules.payments.schema import (
    PaymentCreate,
    PaymentRead,
    PaymentUpdate,
)
from app.modules.payments.service import PaymentService
from app.modules.users.model import User
from app.shared.deps.auth import require_admin

router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)

def get_payment_service(
    db: Session = Depends(get_db),
) -> PaymentService:
    return PaymentService(db)

@router.post(
    "",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    payload: PaymentCreate,
    current_user: User = Depends(require_admin),
    service: PaymentService = Depends(get_payment_service),
):
    return service.create(
        payload=payload,
        current_user=current_user,
    )


@router.get(
    "",
    response_model=list[PaymentRead],
)
def list_payments(
    start_date: date | None = Query(
        default=None,
        description="Data inicial do período.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Data final do período.",
    ),
    current_user: User = Depends(require_admin),
    service: PaymentService = Depends(get_payment_service),
):
    return service.list(
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
)
def get_payment(
    payment_id: int,
    current_user: User = Depends(require_admin),
    service: PaymentService = Depends(get_payment_service),
):
    return service.get_by_id(payment_id)


@router.patch(
    "/{payment_id}",
    response_model=PaymentRead,
)
def update_payment(
    payment_id: int,
    payload: PaymentUpdate,
    current_user: User = Depends(require_admin),
    service: PaymentService = Depends(get_payment_service),
):
    return service.update(
        payment_id=payment_id,
        payload=payload,
    )


@router.delete(
    "/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_payment(
    payment_id: int,
    current_user: User = Depends(require_admin),
    service: PaymentService = Depends(get_payment_service),
):
    service.delete(payment_id)