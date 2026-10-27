from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.modules.processes.deps import get_process_service
from app.modules.processes.model import MovementSource, ProcessStatus
from app.modules.processes.schema import (
    MovementCreate,
    MovementRead,
    ProcessCreate,
    ProcessListItem,
    ProcessNoteCreate,
    ProcessNoteRead,
    ProcessNoteUpdate,
    ProcessRead,
    ProcessStatusChange,
    ProcessStatusChangeResponse,
)
from app.modules.processes.service import ProcessService
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

router = APIRouter(tags=["Processes"])


@router.post(
    "/processes",
    response_model=SuccessResponse[ProcessRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 409, 422),
    summary="Cria um novo processo judicial",
)
def create_process(
    payload: ProcessCreate,
    service: ProcessService = Depends(get_process_service),
    current_user: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[ProcessRead]:
    return ok(
        ProcessRead.model_validate(
            service.create_process(payload, created_by=current_user)
        )
    )


@router.get(
    "/processes",
    response_model=PaginatedResponse[ProcessListItem],
    responses=error_responses(401),
    summary="Lista processos com filtros e paginação",
)
def list_processes(
    client_id: int | None = Query(None),
    status_filter: ProcessStatus | None = Query(None, alias="status"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ProcessService = Depends(get_process_service),
    _: User = Depends(
        require_any_permission(
            PermissionKey.PROCESSOS,
            PermissionKey.CLIENTES,
            PermissionKey.AGENDA,
            PermissionKey.TAREFAS,
        )
    ),
) -> PaginatedResponse[ProcessListItem]:
    items, total = service.list_processes(
        client_id=client_id,
        status=status_filter,
        search=search,
        page=page,
        limit=limit,
    )
    return paginated(
        [ProcessListItem.model_validate(p) for p in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/processes/{process_id}",
    response_model=SuccessResponse[ProcessRead],
    responses=error_responses(401, 404),
    summary="Retorna dados de um processo",
)
def get_process(
    process_id: int,
    service: ProcessService = Depends(get_process_service),
    _: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[ProcessRead]:
    return ok(ProcessRead.model_validate(service.get_process(process_id)))


@router.patch(
    "/processes/{process_id}/status",
    response_model=SuccessResponse[ProcessStatusChangeResponse],
    responses=error_responses(401, 404, 409, 422),
    summary="Altera o status do processo e registra movimentação SYSTEM",
)
def change_process_status(
    process_id: int,
    payload: ProcessStatusChange,
    service: ProcessService = Depends(get_process_service),
    current_user: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[ProcessStatusChangeResponse]:
    process, movement = service.change_status(process_id, payload, current_user)
    return ok(ProcessStatusChangeResponse.from_process(process, movement.id))


@router.post(
    "/processes/{process_id}/movements",
    response_model=SuccessResponse[MovementRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 422),
    summary="Registra movimentação manual em um processo",
)
def create_movement(
    process_id: int,
    payload: MovementCreate,
    service: ProcessService = Depends(get_process_service),
    current_user: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[MovementRead]:
    return ok(
        MovementRead.model_validate(
            service.create_movement(process_id, payload, created_by=current_user)
        )
    )


@router.get(
    "/processes/{process_id}/movements",
    response_model=PaginatedResponse[MovementRead],
    responses=error_responses(401, 404),
    summary="Lista movimentações de um processo em ordem cronológica decrescente",
)
def list_movements(
    process_id: int,
    source: MovementSource | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ProcessService = Depends(get_process_service),
    _: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> PaginatedResponse[MovementRead]:
    items, total = service.list_movements(
        process_id,
        source=source,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return paginated(
        [MovementRead.model_validate(m) for m in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post(
    "/processes/{process_id}/notes",
    response_model=SuccessResponse[ProcessNoteRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 422),
    summary="Cria uma anotação interna vinculada ao processo",
)
def create_process_note(
    process_id: int,
    payload: ProcessNoteCreate,
    service: ProcessService = Depends(get_process_service),
    current_user: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[ProcessNoteRead]:
    return ok(
        ProcessNoteRead.model_validate(
            service.create_note(process_id, payload, current_user=current_user)
        )
    )


@router.get(
    "/processes/{process_id}/notes",
    response_model=PaginatedResponse[ProcessNoteRead],
    responses=error_responses(401, 404),
    summary="Lista anotações internas do processo em ordem cronológica decrescente",
)
def list_process_notes(
    process_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ProcessService = Depends(get_process_service),
    _: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> PaginatedResponse[ProcessNoteRead]:
    items, total = service.list_notes(process_id, page=page, limit=limit)
    return paginated(
        [ProcessNoteRead.model_validate(n) for n in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.patch(
    "/processes/{process_id}/notes/{note_id}",
    response_model=SuccessResponse[ProcessNoteRead],
    responses=error_responses(401, 403, 404, 422),
    summary="Edita uma anotação (apenas autor ou admin)",
)
def update_process_note(
    process_id: int,
    note_id: int,
    payload: ProcessNoteUpdate,
    service: ProcessService = Depends(get_process_service),
    current_user: User = Depends(require_permission(PermissionKey.PROCESSOS)),
) -> SuccessResponse[ProcessNoteRead]:
    return ok(
        ProcessNoteRead.model_validate(
            service.update_note(process_id, note_id, payload, current_user=current_user)
        )
    )


@router.get(
    "/clients/{client_id}/processes",
    response_model=PaginatedResponse[ProcessListItem],
    responses=error_responses(401, 404),
    summary="Lista processos de um cliente específico",
)
def list_processes_by_client(
    client_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ProcessService = Depends(get_process_service),
    _: User = Depends(
        require_any_permission(PermissionKey.PROCESSOS, PermissionKey.CLIENTES)
    ),
) -> PaginatedResponse[ProcessListItem]:
    items, total = service.list_by_client(client_id, page=page, limit=limit)
    return paginated(
        [ProcessListItem.model_validate(p) for p in items],
        total=total,
        page=page,
        limit=limit,
    )
