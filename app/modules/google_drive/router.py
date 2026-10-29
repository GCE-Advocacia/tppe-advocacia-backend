import logging

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse

from app.config.settings import get_settings
from app.modules.google_drive.deps import get_google_drive_service
from app.modules.google_drive.schema import (
    GoogleDriveAuthUrlRead,
    GoogleDriveStatusRead,
)
from app.modules.google_drive.service import GoogleDriveService
from app.modules.users.model import User
from app.shared.deps.auth import get_current_user, require_admin
from app.shared.http.responses import SuccessResponse, error_responses, ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/google-drive", tags=["Google Drive"])


@router.get(
    "/status",
    response_model=SuccessResponse[GoogleDriveStatusRead],
    responses=error_responses(401),
    summary="Indica se o Google Drive do escritório está conectado",
)
def get_google_drive_status(
    service: GoogleDriveService = Depends(get_google_drive_service),
    _: User = Depends(get_current_user),
) -> SuccessResponse[GoogleDriveStatusRead]:
    return ok(service.get_status())


@router.get(
    "/auth-url",
    response_model=SuccessResponse[GoogleDriveAuthUrlRead],
    responses=error_responses(401, 403, 503),
    summary="Retorna a URL de consentimento do Google Drive (admin only)",
)
def get_google_drive_auth_url(
    service: GoogleDriveService = Depends(get_google_drive_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[GoogleDriveAuthUrlRead]:
    return ok(GoogleDriveAuthUrlRead(auth_url=service.build_auth_url(current_user.id)))


@router.get(
    "/callback",
    summary="Callback OAuth do Google Drive — troca o code por tokens",
)
def google_drive_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    service: GoogleDriveService = Depends(get_google_drive_service),
) -> RedirectResponse:
    base = f"{get_settings().frontend_url.rstrip('/')}/sistema/processos"
    result = "error"
    if not error and code and state:
        try:
            service.handle_callback(code, state)
            result = "connected"
        except Exception:
            logger.exception("Google Drive OAuth callback failed")
    return RedirectResponse(
        f"{base}?google_drive={result}", status_code=status.HTTP_302_FOUND
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403),
    summary="Desconecta o Google Drive do escritório (admin only)",
)
def disconnect_google_drive(
    service: GoogleDriveService = Depends(get_google_drive_service),
    _: User = Depends(require_admin),
) -> Response:
    service.disconnect()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
