from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.deadlines.deps import get_deadline_service
from app.modules.deadlines.schema import (
    DeadlineAlertKind,
    DeadlineAlertRead,
    DeadlineCalculateRequest,
    DeadlineCalculateResponse,
    DeadlineCreate,
    DeadlineRead,
    DeadlineUpdate,
)
from app.modules.deadlines.service import EXPIRED_DAYS_BEFORE, DeadlineService
from app.modules.users.model import User
from app.shared.deps.auth import require_any_permission, require_permission
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.types import PermissionKey

router = APIRouter(tags=["Deadlines"])


@router.post(
    "/deadlines/calculate",
    response_model=SuccessResponse[DeadlineCalculateResponse],
    responses=error_responses(401, 422),
    summary="Calcula data-limite em dias úteis sem persistir",
)
def calculate_deadline(
    payload: DeadlineCalculateRequest,
    service: DeadlineService = Depends(get_deadline_service),
    _: User = Depends(
        require_any_permission(PermissionKey.AGENDA, PermissionKey.PROCESSOS)
    ),
) -> SuccessResponse[DeadlineCalculateResponse]:
    due_date, skipped = service.calculate_due_date(
        start_date=payload.start_date,
        business_days=payload.business_days,
        court=payload.court,
        comarca=payload.comarca,
    )
    return ok(
        DeadlineCalculateResponse(
            start_date=payload.start_date,
            business_days=payload.business_days,
            due_date=due_date,
            court=payload.court,
            comarca=payload.comarca,
            skipped_days=skipped,
        )
    )


@router.post(
    "/processes/{process_id}/deadlines",
    response_model=SuccessResponse[DeadlineRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 422),
    summary="Cria prazo persistido vinculado ao processo",
)
def create_deadline(
    process_id: int,
    payload: DeadlineCreate,
    service: DeadlineService = Depends(get_deadline_service),
    current_user: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[DeadlineRead]:
    deadline = service.create_for_process(
        process_id, payload, created_by_id=current_user.id
    )
    return ok(DeadlineRead.model_validate(deadline))


@router.get(
    "/processes/{process_id}/deadlines",
    response_model=PaginatedResponse[DeadlineRead],
    responses=error_responses(401, 404),
    summary="Lista prazos de um processo",
)
def list_deadlines(
    process_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: DeadlineService = Depends(get_deadline_service),
    _: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> PaginatedResponse[DeadlineRead]:
    items, total = service.list_by_process(process_id, page=page, limit=limit)
    return paginated(
        [DeadlineRead.model_validate(d) for d in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.patch(
    "/deadlines/{deadline_id}",
    response_model=SuccessResponse[DeadlineRead],
    responses=error_responses(401, 404, 422),
    summary="Atualiza prazo (recalcula due_date se start/business_days/comarca mudarem)",
)
def update_deadline(
    deadline_id: int,
    payload: DeadlineUpdate,
    service: DeadlineService = Depends(get_deadline_service),
    _: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[DeadlineRead]:
    return ok(DeadlineRead.model_validate(service.update(deadline_id, payload)))


@router.delete(
    "/deadlines/{deadline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 404),
    summary="Remove um prazo",
)
def delete_deadline(
    deadline_id: int,
    service: DeadlineService = Depends(get_deadline_service),
    _: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> Response:
    service.delete(deadline_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/processes/{process_id}/deadlines/{deadline_id}/alerts",
    response_model=SuccessResponse[list[DeadlineAlertRead]],
    responses=error_responses(401, 403, 404),
    summary="Lista o histórico de alertas disparados de um prazo (admin/autor)",
)
def list_deadline_alerts(
    process_id: int,
    deadline_id: int,
    service: DeadlineService = Depends(get_deadline_service),
    current_user: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[list[DeadlineAlertRead]]:
    alerts = service.list_alerts(process_id, deadline_id, current_user)
    return ok(
        [
            DeadlineAlertRead(
                id=a.id,
                deadline_id=a.deadline_id,
                days_before=a.days_before,
                kind=(
                    DeadlineAlertKind.EXPIRED
                    if a.days_before == EXPIRED_DAYS_BEFORE
                    else DeadlineAlertKind.APPROACHING
                ),
                sent_at=a.sent_at,
            )
            for a in alerts
        ]
    )
