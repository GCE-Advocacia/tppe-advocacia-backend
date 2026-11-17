from fastapi import APIRouter, Depends

from app.modules.notifications.deps import get_notification_service
from app.modules.notifications.schema import PreferencesRead, PreferencesUpdate
from app.modules.notifications.service import NotificationService
from app.modules.users.model import User
from app.shared.deps.auth import require_permission
from app.shared.http.responses import SuccessResponse, error_responses, ok
from app.shared.types import PermissionKey

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "/preferences",
    response_model=SuccessResponse[PreferencesRead],
    responses=error_responses(401),
    summary="Obtém preferências de notificação do usuário autenticado",
)
def get_preferences(
    service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission(PermissionKey.NOTIFICACOES)),
) -> SuccessResponse[PreferencesRead]:
    prefs = service.get_preferences(current_user.id)
    return ok(PreferencesRead(preferences=prefs))


@router.patch(
    "/preferences",
    response_model=SuccessResponse[PreferencesRead],
    responses=error_responses(401, 422),
    summary="Atualiza preferências de notificação do usuário autenticado",
)
def update_preferences(
    payload: PreferencesUpdate,
    service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission(PermissionKey.NOTIFICACOES)),
) -> SuccessResponse[PreferencesRead]:
    prefs = service.update_preferences(current_user.id, payload.preferences)
    return ok(PreferencesRead(preferences=prefs))
