from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.database import get_db
from app.modules.email_outbox.logs_service import EmailLogService
from app.modules.email_outbox.model import EmailStatus
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.schema import (
    EmailHealthRead,
    EmailLogDetail,
    EmailLogRead,
    EmailTypeRead,
    ResendBatchRequest,
    ResendBatchResult,
)
from app.modules.email_outbox.service import EmailOutbox
from app.modules.users.model import User
from app.shared.deps.auth import require_admin
from app.shared.exceptions import AppException
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)

router = APIRouter(prefix="/email-logs", tags=["Email logs"])


def get_email_log_service(db: Session = Depends(get_db)) -> EmailLogService:
    return EmailLogService(EmailOutbox(EmailOutboxRepository(db)), get_settings())


@router.get(
    "",
    response_model=PaginatedResponse[EmailLogRead],
    responses=error_responses(400, 401, 403),
    summary="Histórico de e-mails com filtros e paginação",
)
def list_email_logs(
    inicio: date | None = Query(None, description="Data inicial (Brasília)"),
    fim: date | None = Query(None, description="Data final (Brasília)"),
    status: EmailStatus | None = Query(None),
    tipo: str | None = Query(None, max_length=100, description="Id do template"),
    busca: str | None = Query(
        None, max_length=200, description="Destinatário ou assunto"
    ),
    related_type: str | None = Query(None, max_length=50),
    related_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: EmailLogService = Depends(get_email_log_service),
    _: User = Depends(require_admin),
) -> PaginatedResponse[EmailLogRead]:
    if inicio and fim and inicio > fim:
        raise AppException(
            http_status.HTTP_400_BAD_REQUEST,
            "INVALID_PERIOD",
            "A data inicial não pode ser maior que a data final",
        )
    items, total = service.search(
        start=inicio,
        end=fim,
        status=status,
        template=tipo,
        search=busca,
        related_type=related_type,
        related_id=related_id,
        page=page,
        limit=limit,
    )
    return paginated(items, total=total, page=page, limit=limit)


@router.get(
    "/health",
    response_model=SuccessResponse[EmailHealthRead],
    responses=error_responses(401, 403),
    summary="Saúde do envio: provedores, fila, taxa de sucesso e envios por dia",
)
def email_health(
    service: EmailLogService = Depends(get_email_log_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[EmailHealthRead]:
    return ok(service.health())


@router.get(
    "/types",
    response_model=SuccessResponse[list[EmailTypeRead]],
    responses=error_responses(401, 403),
    summary="Tipos de e-mail para o filtro",
)
def email_types(
    service: EmailLogService = Depends(get_email_log_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[list[EmailTypeRead]]:
    return ok(service.types())


@router.post(
    "/resend",
    response_model=SuccessResponse[ResendBatchResult],
    responses=error_responses(401, 403, 422),
    summary="Reenvia vários e-mails de uma vez",
)
def resend_many(
    payload: ResendBatchRequest,
    service: EmailLogService = Depends(get_email_log_service),
    admin: User = Depends(require_admin),
) -> SuccessResponse[ResendBatchResult]:
    return ok(service.resend_many(payload.ids, admin.id))


@router.get(
    "/{email_id}",
    response_model=SuccessResponse[EmailLogDetail],
    responses=error_responses(401, 403, 404),
    summary="E-mail com tentativas e o HTML como saiu",
)
def get_email_log(
    email_id: str,
    service: EmailLogService = Depends(get_email_log_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[EmailLogDetail]:
    return ok(service.detail(email_id))


@router.post(
    "/{email_id}/resend",
    response_model=SuccessResponse[EmailLogRead],
    status_code=201,
    responses=error_responses(401, 403, 404, 409),
    summary="Põe uma cópia do e-mail na fila",
)
def resend_email(
    email_id: str,
    service: EmailLogService = Depends(get_email_log_service),
    admin: User = Depends(require_admin),
) -> SuccessResponse[EmailLogRead]:
    return ok(service.resend(email_id, admin.id))


@router.post(
    "/{email_id}/cancel",
    response_model=SuccessResponse[EmailLogRead],
    responses=error_responses(401, 403, 404, 409),
    summary="Cancela um e-mail pendente ou com falha",
)
def cancel_email(
    email_id: str,
    service: EmailLogService = Depends(get_email_log_service),
    _: User = Depends(require_admin),
) -> SuccessResponse[EmailLogRead]:
    return ok(service.cancel(email_id))
