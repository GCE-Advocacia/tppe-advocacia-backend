from fastapi import APIRouter, Depends, Query

from app.modules.users.deps import get_user_service
from app.modules.users.model import User
from app.modules.users.schema import UserCreate, UserRead, UserUpdate
from app.modules.users.service import UserService
from app.shared.deps.auth import require_admin, require_any_permission
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.types import PermissionKey, Role

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=PaginatedResponse[UserRead],
    responses=error_responses(401, 403),
    summary="Lista usuários com filtros e paginação",
)
def list_users(
    role: Role | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(
        require_any_permission(
            PermissionKey.LEADS, PermissionKey.TAREFAS, PermissionKey.PROCESSOS
        )
    ),
) -> PaginatedResponse[UserRead]:
    # Funcionários só usam a lista como seletor de responsáveis ativos.
    if current_user.role != Role.ADMIN:
        role, is_active = None, True
    items, total = service.list_users(
        role=role, is_active=is_active, page=page, limit=limit
    )
    return paginated(
        [UserRead.model_validate(u) for u in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post(
    "",
    status_code=201,
    response_model=SuccessResponse[UserRead],
    responses=error_responses(401, 403, 409, 422),
    summary="Cria um novo usuário",
)
def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[UserRead]:
    return ok(
        UserRead.model_validate(service.create_user(payload, created_by=current_user))
    )


@router.get(
    "/{user_id}",
    response_model=SuccessResponse[UserRead],
    responses=error_responses(401, 403, 404),
    summary="Obtém um usuário por ID",
)
def get_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[UserRead]:
    return ok(UserRead.model_validate(service.get_user(user_id)))


@router.patch(
    "/{user_id}",
    response_model=SuccessResponse[UserRead],
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Atualiza dados do usuário, papel ou status",
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[UserRead]:
    return ok(
        UserRead.model_validate(
            service.update_user(user_id, payload, updated_by=current_user)
        )
    )
