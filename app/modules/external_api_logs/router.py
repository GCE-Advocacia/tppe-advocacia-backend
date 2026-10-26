from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.modules.external_api_logs.deps import get_external_api_log_service
from app.modules.external_api_logs.model import ExternalApiProvider, ExternalApiStatus
from app.modules.external_api_logs.schema import ExternalApiLogRead
from app.modules.external_api_logs.service import ExternalApiLogService
from app.modules.users.model import User
from app.shared.deps.auth import require_permission
from app.shared.http.responses import PaginatedResponse, error_responses, paginated
from app.shared.types import PermissionKey

router = APIRouter(prefix="/external-api-logs", tags=["External API Logs"])


@router.get(
    "",
    response_model=PaginatedResponse[ExternalApiLogRead],
    responses=error_responses(401, 403),
    summary="Lista logs de chamadas a APIs externas",
)
def list_external_api_logs(
    provider: ExternalApiProvider | None = Query(None),
    status: ExternalApiStatus | None = Query(None),
    process_id: int | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ExternalApiLogService = Depends(get_external_api_log_service),
    _: User = Depends(require_permission(PermissionKey.LOGS_API)),
) -> PaginatedResponse[ExternalApiLogRead]:
    items, total = service.list_logs(
        provider=provider,
        status=status,
        process_id=process_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return paginated(
        [ExternalApiLogRead.model_validate(log) for log in items],
        total=total,
        page=page,
        limit=limit,
    )
