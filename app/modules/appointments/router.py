from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.appointments.deps import get_appointment_service
from app.modules.appointments.model import AppointmentType
from app.modules.appointments.schema import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
)
from app.modules.appointments.service import AppointmentService
from app.modules.users.model import User
from app.shared.deps.auth import require_permission
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.types import PermissionKey

router = APIRouter(prefix="/appointments", tags=["Appointments"])

# TODO: endpoint para listar todos os compromissos do mesmo que o usuário, para exibir no calendário.


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[AppointmentRead],
    responses=error_responses(401, 422),
    summary="Cria um compromisso na agenda",
)
def create_appointment(
    payload: AppointmentCreate,
    service: AppointmentService = Depends(get_appointment_service),
    current_user: User = Depends(require_permission(PermissionKey.AGENDA)),
) -> SuccessResponse[AppointmentRead]:
    appointment = service.create_appointment(payload, current_user)
    return ok(AppointmentRead.model_validate(appointment))


@router.get(
    "",
    response_model=PaginatedResponse[AppointmentRead],
    responses=error_responses(401),
    summary="Lista os compromissos do usuário autenticado, com filtros",
)
def list_appointments(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    type: AppointmentType | None = Query(None),
    client_id: int | None = Query(None),
    process_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: AppointmentService = Depends(get_appointment_service),
    current_user: User = Depends(require_permission(PermissionKey.AGENDA)),
) -> PaginatedResponse[AppointmentRead]:
    items, total = service.list_appointments(
        current_user,
        date_from=date_from,
        date_to=date_to,
        type=type,
        client_id=client_id,
        process_id=process_id,
        page=page,
        limit=limit,
    )
    return paginated(
        [AppointmentRead.model_validate(a) for a in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{appointment_id}",
    response_model=SuccessResponse[AppointmentRead],
    responses=error_responses(401, 403, 404),
    summary="Retorna os detalhes de um compromisso",
)
def get_appointment(
    appointment_id: int,
    service: AppointmentService = Depends(get_appointment_service),
    current_user: User = Depends(require_permission(PermissionKey.AGENDA)),
) -> SuccessResponse[AppointmentRead]:
    appointment = service.get_appointment(appointment_id, current_user)
    return ok(AppointmentRead.model_validate(appointment))


@router.patch(
    "/{appointment_id}",
    response_model=SuccessResponse[AppointmentRead],
    responses=error_responses(401, 403, 404, 422),
    summary="Atualiza parcialmente um compromisso",
)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    service: AppointmentService = Depends(get_appointment_service),
    current_user: User = Depends(require_permission(PermissionKey.AGENDA)),
) -> SuccessResponse[AppointmentRead]:
    appointment = service.update_appointment(appointment_id, payload, current_user)
    return ok(AppointmentRead.model_validate(appointment))


@router.delete(
    "/{appointment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
    summary="Remove um compromisso",
)
def delete_appointment(
    appointment_id: int,
    service: AppointmentService = Depends(get_appointment_service),
    current_user: User = Depends(require_permission(PermissionKey.AGENDA)),
) -> Response:
    service.delete_appointment(appointment_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
