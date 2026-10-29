from fastapi import APIRouter, Depends, Request

from app.modules.email_settings.deps import get_email_settings_service
from app.modules.email_settings.model import EmailIdentity, EmailProfile
from app.modules.email_settings.schema import (
    ConnectionStepRead,
    ConnectionTestRead,
    EmailIdentityRead,
    EmailIdentityUpdate,
    EmailOverviewRead,
    EmailProfileForm,
    EmailProfileRead,
    EmailProfileUpdate,
    EmailStatusRead,
    ProviderPresetRead,
    TestSendMeRead,
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
        preset=profile.preset,
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
        warnings=EmailSettingsService.warnings(profile),
    )


def _identity(identity: EmailIdentity) -> EmailIdentityRead:
    return EmailIdentityRead(
        from_name=identity.from_name,
        reply_to=identity.reply_to,
        version=identity.version or 1,
        updated_at=identity.updated_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[EmailOverviewRead],
    summary="Identidade do escritório, conta própria e conta do sistema",
    responses=error_responses(401, 403),
)
def get_overview(
    _: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[EmailOverviewRead]:
    profiles = service.list_profiles()
    return ok(
        EmailOverviewRead(
            identity=_identity(service.get_identity()),
            own_account=_read(profiles[0]) if profiles else None,
            system_account_email=service.system_account_email(),
            system_account_configured=service.system_account_email() is not None,
        )
    )


@router.put(
    "/identity",
    response_model=SuccessResponse[EmailIdentityRead],
    summary="Salva o nome do remetente e o responder para do escritório",
    responses=error_responses(401, 403, 409, 422),
)
def update_identity(
    payload: EmailIdentityUpdate,
    current_user: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[EmailIdentityRead]:
    return ok(_identity(service.update_identity(payload, current_user)))


@router.get(
    "/presets",
    response_model=SuccessResponse[list[ProviderPresetRead]],
    summary="Provedores da lista, com servidor, porta e ajuda da senha de app",
    responses=error_responses(401, 403),
)
def list_presets(
    _: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[list[ProviderPresetRead]]:
    return ok(
        [
            ProviderPresetRead(
                id=p.id,
                name=p.name,
                host=p.host,
                port=p.port,
                security=p.security,
                password_help=p.password_help,
                help_url=p.help_url,
                sender_must_match=p.sender_must_match,
            )
            for p in service.presets()
        ]
    )


@router.get(
    "/status",
    response_model=SuccessResponse[EmailStatusRead],
    summary="Se o envio está funcionando, conta em uso e último envio",
    responses=error_responses(401, 403),
)
def get_status(
    _: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[EmailStatusRead]:
    return ok(service.status())


@router.post(
    "/test-send-me",
    response_model=SuccessResponse[TestSendMeRead],
    summary="Envia um e-mail de teste para o e-mail do admin logado",
    responses=error_responses(401, 403, 429, 502),
)
@limiter.limit("5/minute", key_func=user_key)
def test_send_me(
    request: Request,
    current_user: User = Depends(require_admin),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> SuccessResponse[TestSendMeRead]:
    return ok(service.test_send_me(current_user))


@router.get(
    "/profiles",
    response_model=SuccessResponse[list[EmailProfileRead]],
    summary="Conta própria do escritório, sem a senha",
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
                    step=s.step,
                    ok=s.ok,
                    duration_ms=s.duration_ms,
                    error=s.error,
                    hint=s.hint,
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
