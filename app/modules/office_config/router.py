from fastapi import APIRouter, Depends

from app.modules.office_config.deps import (
    get_office_config_service,
    get_theme_service,
)
from app.modules.office_config.schema import (
    OfficeConfigRead,
    OfficeConfigUpdate,
    ThemeCreate,
    ThemeQuotaRead,
    ThemeRead,
    ThemeUpdate,
)
from app.modules.office_config.service import OfficeConfigService, ThemeService
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
