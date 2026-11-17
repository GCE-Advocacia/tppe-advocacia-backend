from fastapi import APIRouter, Depends

from app.modules.permissions.deps import get_permission_service
from app.modules.permissions.schema import PermissionRead
from app.modules.permissions.service import PermissionService
from app.modules.users.model import User
from app.shared.deps.auth import require_admin
from app.shared.http.responses import SuccessResponse, error_responses, ok

router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.get(
    "",
    response_model=SuccessResponse[list[PermissionRead]],
    responses=error_responses(401, 403),
    summary="Lista o catálogo de permissões por aba (admin)",
)
def list_permissions(
    service: PermissionService = Depends(get_permission_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[list[PermissionRead]]:
    return ok([PermissionRead.model_validate(p) for p in service.list_permissions()])
