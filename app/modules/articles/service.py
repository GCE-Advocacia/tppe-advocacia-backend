import bleach

from app.modules.articles.model import Article, ArticleStatus
from app.modules.articles.repository import ArticleRepository
from app.modules.articles.schema import ArticleCreate, ArticleUpdate
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import ArticleNotFoundError
from app.shared.service.helpers import get_or_raise

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "s", "h1", "h2", "h3", "ul", "ol", "li",
    "a", "img", "blockquote", "code", "pre", "span",
]
ALLOWED_ATTRS = {"a": ["href", "title"], "img": ["src", "alt"], "*": ["class"]}


def sanitize_content(content: str) -> str:
    return bleach.clean(content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)


class ArticleService:
    def __init__(self, repository: ArticleRepository) -> None:
        self.repository = repository

    def create(self, payload: ArticleCreate, author: User) -> Article:
        with unit_of_work(self.repository.db):
            return self.repository.create(
                title=payload.title,
                content=sanitize_content(payload.content),
                category=payload.category,
                author_id=author.id,
                cover_image_url=payload.cover_image_url,
                cover_image_position=payload.cover_image_position,
                status=payload.status,
                summary=payload.summary,
            )

    def update(self, article_id: int, payload: ArticleUpdate) -> Article:
        article = get_or_raise(
            lambda: self.repository.get_by_id(article_id), ArticleNotFoundError
        )
        data = payload.model_dump(exclude_unset=True)
        if "content" in data:
            data["content"] = sanitize_content(data["content"])
        with unit_of_work(self.repository.db):
            return self.repository.update(article, data)

    def get_published_by_id(self, article_id: int) -> Article:
        article = self.repository.get_by_id(article_id)
        if article is None or article.status != ArticleStatus.PUBLISHED:
            raise ArticleNotFoundError()
        return article

    def get_preview(self, article_id: int) -> Article:
        return get_or_raise(
            lambda: self.repository.get_by_id(article_id), ArticleNotFoundError
        )

    def list_published(
        self, page: int = 1, limit: int = 20
    ) -> tuple[list[Article], int]:
        return self.repository.get_published(page=page, limit=limit)

    def list_all(self, page: int = 1, limit: int = 20) -> tuple[list[Article], int]:
        return self.repository.get_all(page=page, limit=limit)
