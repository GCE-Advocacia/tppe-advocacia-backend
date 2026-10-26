from fastapi import APIRouter, Depends, Query, Request

from app.modules.articles.deps import get_article_service
from app.modules.articles.schema import (
    ArticleCreate,
    ArticleListItem,
    ArticleRead,
    ArticleUpdate,
)
from app.modules.articles.service import ArticleService
from app.modules.users.model import User
from app.shared.deps.auth import require_permission
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.types import PermissionKey

router = APIRouter(prefix="/articles", tags=["Articles"])


@router.post(
    "",
    status_code=201,
    response_model=SuccessResponse[ArticleRead],
    responses=error_responses(401, 422),
    summary="Cria um novo artigo",
)
def create_article(
    payload: ArticleCreate,
    service: ArticleService = Depends(get_article_service),
    current_user: User = Depends(require_permission(PermissionKey.ARTIGOS)),
) -> SuccessResponse[ArticleRead]:
    return ok(ArticleRead.model_validate(service.create(payload, current_user)))


@router.patch(
    "/{article_id}",
    response_model=SuccessResponse[ArticleRead],
    responses=error_responses(401, 404, 422),
    summary="Atualiza um artigo",
)
def update_article(
    article_id: int,
    payload: ArticleUpdate,
    service: ArticleService = Depends(get_article_service),
    _: User = Depends(require_permission(PermissionKey.ARTIGOS)),
) -> SuccessResponse[ArticleRead]:
    return ok(ArticleRead.model_validate(service.update(article_id, payload)))


@router.get(
    "/admin",
    response_model=PaginatedResponse[ArticleListItem],
    responses=error_responses(401),
    summary="Lista todos os artigos incluindo rascunhos (autenticado)",
)
def list_all_articles(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ArticleService = Depends(get_article_service),
    _: User = Depends(require_permission(PermissionKey.ARTIGOS)),
) -> PaginatedResponse[ArticleListItem]:
    items, total = service.list_all(page=page, limit=limit)
    return paginated(
        [
            ArticleListItem(
                id=a.id,
                title=a.title,
                summary=a.summary,
                status=a.status,
                created_at=a.created_at,
                url=str(request.url_for("preview_article", article_id=a.id)),
                author_name=a.author.name,
                category=a.category,
            )
            for a in items
        ],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{article_id}/preview",
    response_model=SuccessResponse[ArticleRead],
    responses=error_responses(401, 404),
    summary="Visualiza um artigo independente do status",
)
def preview_article(
    article_id: int,
    service: ArticleService = Depends(get_article_service),
    _: User = Depends(require_permission(PermissionKey.ARTIGOS)),
) -> SuccessResponse[ArticleRead]:
    return ok(ArticleRead.model_validate(service.get_preview(article_id)))


@router.get(
    "/{article_id}",
    response_model=SuccessResponse[ArticleRead],
    responses=error_responses(404),
    summary="Obtém um artigo publicado por ID",
)
def get_article(
    article_id: int,
    service: ArticleService = Depends(get_article_service),
) -> SuccessResponse[ArticleRead]:
    return ok(ArticleRead.model_validate(service.get_published_by_id(article_id)))


@router.get(
    "",
    response_model=PaginatedResponse[ArticleListItem],
    summary="Lista artigos publicados",
)
def list_articles(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ArticleService = Depends(get_article_service),
) -> PaginatedResponse[ArticleListItem]:
    items, total = service.list_published(page=page, limit=limit)
    return paginated(
        [
            ArticleListItem(
                id=a.id,
                title=a.title,
                summary=a.summary,
                status=a.status,
                created_at=a.created_at,
                url=str(request.url_for("get_article", article_id=a.id)),
                author_name=a.author.name,
                category=a.category,
            )
            for a in items
        ],
        total=total,
        page=page,
        limit=limit,
    )
