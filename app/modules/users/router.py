from fastapi import APIRouter, Depends, Query

from app.modules.users.deps import get_invite_service, get_user_service
from app.modules.users.invite_model import UserInvite
from app.modules.users.invite_service import InviteService, invite_status
from app.modules.users.model import User
from app.modules.users.schema import InviteSummary, UserCreate, UserRead, UserUpdate
from app.modules.users.service import UserService
from app.shared.deps.auth import require_admin
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.types import Role

router = APIRouter(prefix="/users", tags=["Users"])


def _read(user: User, invite: UserInvite | None) -> UserRead:
    data = UserRead.model_validate(user)
    status = invite_status(invite)
    if invite is not None and status is not None:
        data.invite = InviteSummary(
            status=status, sent_at=invite.created_at, expires_at=invite.expires_at
        )
    return data


def _read_one(user: User, service: UserService) -> UserRead:
    return _read(user, service.latest_invites([user]).get(user.id))


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
    _: User = Depends(require_admin),
) -> PaginatedResponse[UserRead]:
    items, total = service.list_users(
        role=role, is_active=is_active, page=page, limit=limit
    )
    invites = service.latest_invites(items)
    return paginated(
        [_read(u, invites.get(u.id)) for u in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post(
    "",
    status_code=201,
    response_model=SuccessResponse[UserRead],
    responses=error_responses(401, 403, 409, 422),
    summary="Cria um usuário e envia o convite por link",
)
def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[UserRead]:
    user = service.create_user(payload, created_by=current_user)
    return ok(_read_one(user, service))


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
    return ok(_read_one(service.get_user(user_id), service))


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
    user = service.update_user(user_id, payload, updated_by=current_user)
    return ok(_read_one(user, service))


@router.post(
    "/{user_id}/invite/resend",
    response_model=SuccessResponse[UserRead],
    responses=error_responses(400, 401, 403, 404, 429),
    summary="Reenvia o convite (o link anterior deixa de valer)",
)
def resend_invite(
    user_id: int,
    invites: InviteService = Depends(get_invite_service),
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[UserRead]:
    invite = invites.resend(user_id, current_user)
    return ok(_read(service.get_user(user_id), invite))


@router.delete(
    "/{user_id}/invite",
    response_model=SuccessResponse[UserRead],
    responses=error_responses(400, 401, 403, 404),
    summary="Cancela o convite pendente",
)
def cancel_invite(
    user_id: int,
    invites: InviteService = Depends(get_invite_service),
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[UserRead]:
    invites.cancel(user_id, current_user)
    return ok(_read_one(service.get_user(user_id), service))
