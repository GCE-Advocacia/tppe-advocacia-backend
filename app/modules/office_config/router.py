from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from app.modules.office_config.deps import (
    get_office_config_service,
    get_theme_service,
)
from app.modules.office_config.schema import (
    LogoSettingsUpdate,
    LogoSlot,
    OfficeConfigRead,
    OfficeConfigUpdate,
    ThemeCreate,
    ThemeQuotaRead,
    ThemeRead,
    ThemeUpdate,
)
from app.modules.office_config.service import (
    OfficeConfigService,
    ThemeService,
)
from app.modules.users.model import User
from app.shared.deps.auth import require_admin
from app.shared.http.responses import SuccessResponse, error_responses, ok

router = APIRouter(prefix="/office-config", tags=["Office Config"])


@router.get(
    "",
    response_model=SuccessResponse[OfficeConfigRead],
    summary="Retorna a configuração atual do escritório",
)
def get_office_config(
    service: OfficeConfigService = Depends(get_office_config_service),
) -> SuccessResponse[OfficeConfigRead]:
    return ok(OfficeConfigRead.model_validate(service.get()))


@router.patch(
    "",
    response_model=SuccessResponse[OfficeConfigRead],
    responses=error_responses(401, 403),
    summary="Atualiza a configuração do escritório (admin only)",
)
def update_office_config(
    payload: OfficeConfigUpdate,
    service: OfficeConfigService = Depends(get_office_config_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[OfficeConfigRead]:
    return ok(OfficeConfigRead.model_validate(service.update(payload)))


@router.get(
    "/themes",
    response_model=SuccessResponse[list[ThemeRead]],
    summary="Lista todos os temas da landing page",
)
def list_themes(
    service: ThemeService = Depends(get_theme_service),
) -> SuccessResponse[list[ThemeRead]]:
    themes = service.list()
    return ok([ThemeRead.model_validate(t) for t in themes])


@router.get(
    "/themes/quota",
    response_model=SuccessResponse[ThemeQuotaRead],
    summary="Retorna a cota e limites de temas da landing page",
)
def get_theme_quota(
    service: ThemeService = Depends(get_theme_service),
) -> SuccessResponse[ThemeQuotaRead]:
    quota = service.get_quota()
    return ok(ThemeQuotaRead.model_validate(quota))


@router.post(
    "/themes",
    response_model=SuccessResponse[ThemeRead],
    status_code=201,
    responses=error_responses(400, 401, 403, 422),
    summary="Cria um novo tema personalizado para a landing page (admin only)",
)
def create_theme(
    payload: ThemeCreate,
    service: ThemeService = Depends(get_theme_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[ThemeRead]:
    theme = service.create(payload)
    return ok(ThemeRead.model_validate(theme))


@router.put(
    "/themes/{theme_id}",
    response_model=SuccessResponse[ThemeRead],
    responses=error_responses(400, 401, 403, 404, 422),
    summary="Atualiza um tema existente (admin only)",
)
def update_theme(
    theme_id: int,
    payload: ThemeUpdate,
    service: ThemeService = Depends(get_theme_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[ThemeRead]:
    theme = service.update(theme_id, payload)
    return ok(ThemeRead.model_validate(theme))


@router.delete(
    "/themes/{theme_id}",
    status_code=204,
    responses=error_responses(400, 401, 403, 404),
    summary="Exclui um tema personalizado (admin only)",
)
def delete_theme(
    theme_id: int,
    service: ThemeService = Depends(get_theme_service),
    _: User = Depends(require_admin),
) -> None:
    service.delete(theme_id)


@router.post(
    "/themes/{theme_id}/apply",
    response_model=SuccessResponse[OfficeConfigRead],
    responses=error_responses(400, 401, 403, 404),
    summary="Aplica a paleta de cores de um tema na landing page (admin only)",
)
def apply_theme(
    theme_id: int,
    service: ThemeService = Depends(get_theme_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[OfficeConfigRead]:
    config = service.apply(theme_id)
    return ok(OfficeConfigRead.model_validate(config))


@router.put(
    "/logo",
    response_model=SuccessResponse[OfficeConfigRead],
    responses=error_responses(401, 403, 413, 415, 422),
    summary="Substitui e salva a logo do escritório (admin only)",
)
def update_office_logo(
    request: Request,
    file: UploadFile = File(...),
    slot: LogoSlot = "landing-light",
    make_default: bool = Form(False),
    service: OfficeConfigService = Depends(get_office_config_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[OfficeConfigRead]:
    return ok(
        OfficeConfigRead.model_validate(
            service.update_logo(file, str(request.base_url), slot, make_default)
        )
    )


@router.post(
    "/logo/preview",
    responses=error_responses(401, 403, 413, 415, 422),
    summary="Prévia da logo sem salvar (admin only)",
)
def preview_office_logo(
    file: UploadFile = File(...),
    slot: LogoSlot = "landing-light",
    service: OfficeConfigService = Depends(get_office_config_service),
    _: User = Depends(require_admin),
) -> Response:
    return Response(
        service.preview_logo(file, slot),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.delete(
    "/logo",
    response_model=SuccessResponse[OfficeConfigRead],
    responses=error_responses(401, 403),
    summary="Restaura a logo padrão (admin only)",
)
def reset_office_logo(
    request: Request,
    slot: LogoSlot = "landing-light",
    factory: bool = False,
    service: OfficeConfigService = Depends(get_office_config_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[OfficeConfigRead]:
    return ok(
        OfficeConfigRead.model_validate(
            service.reset_logo(str(request.base_url), slot, factory)
        )
    )


@router.patch(
    "/logo",
    response_model=SuccessResponse[OfficeConfigRead],
    responses=error_responses(401, 403, 422),
    summary="Configura o compartilhamento das logos (admin only)",
)
def update_logo_settings(
    payload: LogoSettingsUpdate,
    service: OfficeConfigService = Depends(get_office_config_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[OfficeConfigRead]:
    return ok(OfficeConfigRead.model_validate(service.update_logo_settings(payload)))


@router.post(
    "/logo/default",
    response_model=SuccessResponse[OfficeConfigRead],
    responses=error_responses(401, 403, 422),
    summary="Define a logo atual como padrão (admin only)",
)
def set_office_logo_default(
    request: Request,
    slot: LogoSlot = "landing-light",
    service: OfficeConfigService = Depends(get_office_config_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[OfficeConfigRead]:
    return ok(
        OfficeConfigRead.model_validate(
            service.set_logo_default(str(request.base_url), slot)
        )
    )
