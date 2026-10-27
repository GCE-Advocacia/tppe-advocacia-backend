from functools import lru_cache

from fastapi import Depends

from app.config.settings import get_settings
from app.db.database import SessionLocal
from app.modules.email.branding import OfficeBrandingProvider
from app.modules.email.factory import build_email_service
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.protocol import EmailProvider
from app.modules.email.renderer import EmailRenderer
from app.modules.email.sender import TemplatedEmailSender


@lru_cache(maxsize=1)
def get_email_service() -> FailoverEmailService | FakeEmailService:
    return build_email_service(get_settings())


@lru_cache(maxsize=1)
def get_email_renderer() -> EmailRenderer:
    settings = get_settings()
    return EmailRenderer(
        OfficeBrandingProvider(SessionLocal, fallback_name=settings.smtp_from_name or None),
        system_url=settings.frontend_url,
    )


def get_templated_sender(
    email: EmailProvider = Depends(get_email_service),
    renderer: EmailRenderer = Depends(get_email_renderer),
) -> TemplatedEmailSender:
    return TemplatedEmailSender(renderer, email)


def build_templated_sender() -> TemplatedEmailSender:
    """Para quem roda fora de uma requisição (jobs do scheduler, scripts)."""
    return TemplatedEmailSender(get_email_renderer(), get_email_service())
