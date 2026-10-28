from fastapi import APIRouter, Depends, Request

from app.modules.auth.schema import TokenResponse
from app.modules.users.deps import get_invite_service
from app.modules.users.invite_service import InviteService
from app.modules.users.schema import InviteAccept, InvitePublicRead
from app.shared.http.responses import SuccessResponse, error_responses, ok
from app.shared.limiter import limiter

router = APIRouter(prefix="/invites", tags=["Invites"])


@router.get(
    "/{token}",
    response_model=SuccessResponse[InvitePublicRead],
    responses=error_responses(404, 410),
    summary="Valida o link do convite e devolve nome e e-mail do convidado",
)
@limiter.limit("20/minute")
def get_invite(
    request: Request,
    token: str,
    service: InviteService = Depends(get_invite_service),
) -> SuccessResponse[InvitePublicRead]:
    user = service.get_public(token)
    return ok(InvitePublicRead(name=user.name, email=user.email))


@router.post(
    "/{token}/accept",
    response_model=SuccessResponse[TokenResponse],
    responses=error_responses(404, 410, 422),
    summary="Define a senha pelo convite e já devolve o JWT",
)
@limiter.limit("5/minute")
def accept_invite(
    request: Request,
    token: str,
    payload: InviteAccept,
    service: InviteService = Depends(get_invite_service),
) -> SuccessResponse[TokenResponse]:
    return ok(service.accept(token, payload.password))
