import logging

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse

from app.config.settings import get_settings
from app.modules.appointments.deps import get_appointment_service
from app.modules.appointments.schema import AppointmentSyncResult
from app.modules.appointments.service import AppointmentService
from app.modules.google_calendar.deps import get_google_calendar_service
from app.modules.google_calendar.schema import (
    GoogleAuthUrlRead,
    GooglePullResult,
    GoogleStatusRead,
)
from app.modules.google_calendar.service import GoogleCalendarService
from app.modules.users.model import User
from app.shared.deps.auth import get_current_user
from app.shared.http.responses import SuccessResponse, error_responses, ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/google", tags=["Google Calendar"])


@router.get(
    "/auth-url",
    response_model=SuccessResponse[GoogleAuthUrlRead],
    responses=error_responses(401),
    summary="Retorna a URL de consentimento OAuth do Google",
)
def get_google_auth_url(
    service: GoogleCalendarService = Depends(get_google_calendar_service),
    current_user: User = Depends(get_current_user),
) -> SuccessResponse[GoogleAuthUrlRead]:
    return ok(GoogleAuthUrlRead(auth_url=service.build_auth_url(current_user.id)))


@router.get(
    "/callback",
    summary="Callback OAuth do Google — troca o code por tokens",
)
def google_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    service: GoogleCalendarService = Depends(get_google_calendar_service),
) -> RedirectResponse:
    base = get_settings().frontend_url.rstrip("/")
    if error or not code or not state:
        return RedirectResponse(
            f"{base}/?google_calendar=error", status_code=status.HTTP_302_FOUND
        )
    try:
        service.handle_callback(code, state)
        target = f"{base}/?google_calendar=connected"
    except Exception:
        logger.exception("Google OAuth callback failed")
        target = f"{base}/?google_calendar=error"
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND)


@router.get(
    "/status",
    response_model=SuccessResponse[GoogleStatusRead],
    responses=error_responses(401),
    summary="Indica se o usuário tem o Google Calendar conectado",
)
def get_google_status(
    service: GoogleCalendarService = Depends(get_google_calendar_service),
    current_user: User = Depends(get_current_user),
) -> SuccessResponse[GoogleStatusRead]:
    return ok(service.get_status(current_user.id))


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401),
    summary="Desconecta o Google Calendar do usuário",
)
def disconnect_google(
    service: GoogleCalendarService = Depends(get_google_calendar_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    service.disconnect(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sync-all",
    response_model=SuccessResponse[AppointmentSyncResult],
    responses=error_responses(401, 409, 503),
    summary="Sincroniza ao Google os compromissos futuros ainda não enviados",
)
def sync_all_appointments(
    appointment_service: AppointmentService = Depends(get_appointment_service),
    current_user: User = Depends(get_current_user),
) -> SuccessResponse[AppointmentSyncResult]:
    return ok(appointment_service.sync_all_to_google(current_user))


@router.post(
    "/pull",
    response_model=SuccessResponse[GooglePullResult],
    responses=error_responses(401, 409, 503),
    summary="Importa do Google Calendar os eventos alterados (Google -> sistema)",
)
def pull_from_google(
    service: GoogleCalendarService = Depends(get_google_calendar_service),
    current_user: User = Depends(get_current_user),
) -> SuccessResponse[GooglePullResult]:
    return ok(service.pull_changes(current_user.id))
