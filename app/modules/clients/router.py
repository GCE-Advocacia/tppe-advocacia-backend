from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.clients.deps import get_client_service, get_client_timeline_service
from app.modules.clients.schema import (
    ClientCreate,
    ClientListItem,
    ClientNoteCreate,
    ClientNoteRead,
    ClientNoteUpdate,
    ClientRead,
    ClientTimelineRead,
    ClientUpdate,
)
from app.modules.clients.service import ClientService
from app.modules.clients.timeline_service import ClientTimelineService
from app.modules.users.model import User
from app.shared.deps.auth import (
    require_admin,
    require_any_permission,
    require_permission,
)
from app.shared.exceptions import ConfirmationRequiredError
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.types import PermissionKey

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post(
    "",
    response_model=SuccessResponse[ClientRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 409, 422),
    summary="Cria um novo cliente",
)
def create_client(
    payload: ClientCreate,
    service: ClientService = Depends(get_client_service),
    current_user: User = Depends(require_permission(PermissionKey.CLIENTES)),
) -> SuccessResponse[ClientRead]:
    return ok(
        ClientRead.model_validate(
            service.create_client(payload, created_by=current_user)
        )
    )


@router.get(
    "",
    response_model=PaginatedResponse[ClientListItem],
    responses=error_responses(401),
    summary="Lista clientes com paginação e busca opcional",
)
def list_clients(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ClientService = Depends(get_client_service),
    _: User = Depends(
        require_any_permission(
            PermissionKey.CLIENTES,
            PermissionKey.AGENDA,
            PermissionKey.PAGAMENTOS,
            PermissionKey.PROCESSOS,
            PermissionKey.TAREFAS,
        )
    ),
) -> PaginatedResponse[ClientListItem]:
    items, total = service.list_clients(search=search, page=page, limit=limit)
    return paginated(
        [ClientListItem.model_validate(c) for c in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{client_id}",
    response_model=SuccessResponse[ClientRead],
    responses=error_responses(401, 404),
    summary="Retorna dados de um cliente",
)
def get_client(
    client_id: int,
    service: ClientService = Depends(get_client_service),
    current_user: User = Depends(require_permission(PermissionKey.CLIENTES)),
) -> SuccessResponse[ClientRead]:
    return ok(
        ClientRead.model_validate(service.get_client(client_id, requester=current_user))
    )


@router.patch(
    "/{client_id}",
    response_model=SuccessResponse[ClientRead],
    responses=error_responses(401, 404, 409, 422),
    summary="Atualiza parcialmente um cliente",
)
def update_client(
    client_id: int,
    payload: ClientUpdate,
    service: ClientService = Depends(get_client_service),
    current_user: User = Depends(require_permission(PermissionKey.CLIENTES)),
) -> SuccessResponse[ClientRead]:
    return ok(
        ClientRead.model_validate(
            service.update_client(client_id, payload, updated_by=current_user)
        )
    )


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 401, 403, 404, 409),
    summary="Anonimiza cliente (soft delete LGPD, admin only, exige ?confirm=true)",
)
def anonymize_client(
    client_id: int,
    confirm: bool = Query(
        False, description="Deve ser true para confirmar a ação irreversível"
    ),
    service: ClientService = Depends(get_client_service),
    current_user: User = Depends(require_admin),
) -> Response:
    if not confirm:
        raise ConfirmationRequiredError()
    service.anonymize(client_id, performed_by=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{client_id}/notes",
    response_model=SuccessResponse[ClientNoteRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 422),
    summary="Cria uma observação vinculada ao cliente",
)
def create_note(
    client_id: int,
    payload: ClientNoteCreate,
    service: ClientService = Depends(get_client_service),
    current_user: User = Depends(require_permission(PermissionKey.CLIENTES)),
) -> SuccessResponse[ClientNoteRead]:
    return ok(
        ClientNoteRead.model_validate(
            service.create_note(client_id, payload, current_user=current_user)
        )
    )


@router.get(
    "/{client_id}/notes",
    response_model=PaginatedResponse[ClientNoteRead],
    responses=error_responses(401, 404),
    summary="Lista observações do cliente em ordem cronológica decrescente",
)
def list_notes(
    client_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ClientService = Depends(get_client_service),
    _: User = Depends(require_permission(PermissionKey.CLIENTES)),
) -> PaginatedResponse[ClientNoteRead]:
    items, total = service.list_notes(client_id, page=page, limit=limit)
    return paginated(
        [ClientNoteRead.model_validate(n) for n in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{client_id}/timeline",
    response_model=SuccessResponse[ClientTimelineRead],
    responses=error_responses(401, 404),
    summary="Visão 360º do cliente: notas, processos e feed de atividades",
)
def get_client_timeline(
    client_id: int,
    notes_limit: int = Query(10, ge=1, le=50),
    processes_limit: int = Query(20, ge=1, le=50),
    activity_limit: int = Query(20, ge=1, le=50),
    service: ClientTimelineService = Depends(get_client_timeline_service),
    current_user: User = Depends(require_permission(PermissionKey.CLIENTES)),
) -> SuccessResponse[ClientTimelineRead]:
    return ok(
        service.get_timeline(
            client_id,
            requester=current_user,
            notes_limit=notes_limit,
            processes_limit=processes_limit,
            activity_limit=activity_limit,
        )
    )


@router.patch(
    "/{client_id}/notes/{note_id}",
    response_model=SuccessResponse[ClientNoteRead],
    responses=error_responses(401, 403, 404, 422),
    summary="Edita o conteúdo de uma observação (somente autor ou admin)",
)
def update_note(
    client_id: int,
    note_id: int,
    payload: ClientNoteUpdate,
    service: ClientService = Depends(get_client_service),
    current_user: User = Depends(require_permission(PermissionKey.CLIENTES)),
) -> SuccessResponse[ClientNoteRead]:
    return ok(
        ClientNoteRead.model_validate(
            service.update_note(client_id, note_id, payload, current_user=current_user)
        )
    )
