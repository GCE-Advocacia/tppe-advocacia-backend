from fastapi import APIRouter, Depends, Query

from app.modules.email.renderer import EmailRenderer, UnknownTemplateError
from app.modules.email.schema import (
    EmailTemplatePreviewRead,
    EmailTemplateRead,
    PreviewFormat,
)
from app.modules.users.model import User
from app.shared.deps.auth import require_admin
from app.shared.deps.email import get_email_renderer
from app.shared.exceptions import EmailTemplateNotFoundError
from app.shared.http.responses import SuccessResponse, error_responses, ok

router = APIRouter(prefix="/email", tags=["Email"])


@router.get(
    "/templates",
    response_model=SuccessResponse[list[EmailTemplateRead]],
    summary="Lista os tipos de e-mail do sistema",
    responses=error_responses(401, 403),
)
def list_templates(
    _: User = Depends(require_admin),
    renderer: EmailRenderer = Depends(get_email_renderer),
) -> SuccessResponse[list[EmailTemplateRead]]:
    return ok(
        [
            EmailTemplateRead(id=spec.id, name=spec.name, description=spec.description)
            for spec in renderer.templates.values()
        ]
    )


@router.get(
    "/templates/{template_id}/preview",
    response_model=SuccessResponse[EmailTemplatePreviewRead],
    summary="Pré-visualiza um tipo de e-mail com dados fictícios",
    responses=error_responses(401, 403, 404),
)
def preview_template(
    template_id: str,
    format: PreviewFormat = Query("html"),
    _: User = Depends(require_admin),
    renderer: EmailRenderer = Depends(get_email_renderer),
) -> SuccessResponse[EmailTemplatePreviewRead]:
    try:
        rendered = renderer.render_sample(template_id)
    except UnknownTemplateError as exc:
        raise EmailTemplateNotFoundError() from exc
    return ok(
        EmailTemplatePreviewRead(
            id=template_id,
            format=format,
            subject=rendered.subject,
            content=rendered.html if format == "html" else rendered.text,
        )
    )
