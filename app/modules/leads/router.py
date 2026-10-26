from fastapi import APIRouter, Depends, Query, Request, status

from app.modules.leads.deps import get_lead_service
from app.modules.leads.model import LeadStatus
from app.modules.leads.schema import LeadCreate, LeadRead, LeadUpdate
from app.modules.leads.service import LeadService
from app.modules.users.model import User
from app.shared.deps.auth import require_permission
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.limiter import limiter
from app.shared.types import PermissionKey

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get(
    "",
    response_model=PaginatedResponse[LeadRead],
    responses=error_responses(401, 403),
    summary="Lista os leads cadastrados",
)
def read_leads(
    status: LeadStatus | None = Query(None),
    assigned_to: int | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: LeadService = Depends(get_lead_service),
    _: User = Depends(require_permission(PermissionKey.LEADS)),
) -> PaginatedResponse[LeadRead]:
    leads, total = service.list_leads(
        status=status, assigned_to=assigned_to, page=page, limit=limit
    )
    return paginated(
        [LeadRead.model_validate(lead) for lead in leads],
        total=total,
        page=page,
        limit=limit,
    )


@router.post(
    "",
    response_model=SuccessResponse[LeadRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(409, 422),
    summary="Cria um novo lead (público)",
)
@limiter.limit("5/minute")
def create_new_lead(
    request: Request,
    payload: LeadCreate,
    service: LeadService = Depends(get_lead_service),
) -> SuccessResponse[LeadRead]:
    return ok(LeadRead.model_validate(service.create_lead(payload)))


@router.patch(
    "/{lead_id}",
    response_model=SuccessResponse[LeadRead],
    responses=error_responses(401, 403, 404, 422),
    summary="Atualiza status ou responsável do lead. Retorna 422 se assigned_to não existir.",
)
def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    service: LeadService = Depends(get_lead_service),
    current_user: User = Depends(require_permission(PermissionKey.LEADS)),
) -> SuccessResponse[LeadRead]:
    return ok(
        LeadRead.model_validate(
            service.update_lead(lead_id, payload, current_user=current_user)
        )
    )
