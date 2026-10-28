from fastapi import APIRouter, Depends, Request

from app.modules.email_settings.deps import get_email_settings_service
from app.modules.email_settings.model import EmailProfile
from app.modules.email_settings.schema import (
    ConnectionStepRead,
    ConnectionTestRead,
    EmailProfileForm,
    EmailProfileRead,
    EmailProfileUpdate,
    TestSendRead,
    TestSendRequest,
)
from app.modules.email_settings.service import EmailSettingsService
from app.modules.users.model import User
from app.shared.deps.auth import require_admin
from app.shared.http.responses import SuccessResponse, error_responses, ok
from app.shared.limiter import limiter, user_key

router = APIRouter(prefix="/email-settings", tags=["Email Settings"])


def _read(profile: EmailProfile) -> EmailProfileRead:
    return EmailProfileRead(
        id=profile.id,
        name=profile.name,
        priority=profile.priority,
        provider=profile.provider,
        host=profile.host,
        port=profile.port,
        security=profile.security,
        username=profile.username,
        has_secret=bool(profile.secret_encrypted),
        from_email=profile.from_email,
        from_name=profile.from_name,
        reply_to=profile.reply_to,
        is_active=profile.is_active,
        last_tested_at=profile.last_tested_at,
        last_test_ok=profile.last_test_ok,
        version=profile.version,
        updated_by=profile.updated_by,
        updated_at=profile.updated_at,
    )


@router.get(
    "/profiles",
    response_model=SuccessResponse[list[EmailProfileRead]],
    summary="Lista os perfis de envio (primário e reserva), sem as senhas",
    responses=error_responses(401, 403),
)
def list_profiles(
    _: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[list[EmailProfileRead]]:
    return ok([_read(p) for p in service.list_profiles()])


@router.put(
    "/profiles/{profile_id}",
    response_model=SuccessResponse[EmailProfileRead],
    summary="Salva um perfil (testa a conexão antes; senha vazia mantém a atual)",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def update_profile(
    profile_id: int,
    payload: EmailProfileUpdate,
    current_user: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[EmailProfileRead]:
    return ok(_read(service.update_profile(profile_id, payload, current_user)))


@router.post(
    "/profiles/{profile_id}/test-connection",
    response_model=SuccessResponse[ConnectionTestRead],
    summary="Testa conexão, TLS e login sem enviar e-mail",
    responses=error_responses(401, 403, 404, 422, 503),
)
def test_connection(
    profile_id: int,
    form: EmailProfileForm,
    _: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[ConnectionTestRead]:
    report = service.test_connection(profile_id, form)
    return ok(
        ConnectionTestRead(
            ok=report.ok,
            steps=[
                ConnectionStepRead(
                    step=s.step, ok=s.ok, duration_ms=s.duration_ms, error=s.error
                )
                for s in report.steps
            ],
        )
    )


@router.post(
    "/profiles/{profile_id}/test-send",
    response_model=SuccessResponse[TestSendRead],
    summary="Envia um e-mail de teste de verdade pelo perfil salvo",
    responses=error_responses(401, 403, 404, 422, 429, 502, 503),
)
@limiter.limit("5/minute", key_func=user_key)
def test_send(
    request: Request,
    profile_id: int,
    payload: TestSendRequest,
    current_user: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[TestSendRead]:
    result = service.test_send(profile_id, payload.to, current_user)
    return ok(
        TestSendRead(
            provider=result.provider,
            message_id=result.message_id,
            duration_ms=result.duration_ms,
        )
    )
