import logging
import threading
from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.db.database import SessionLocal
from app.modules.email.branding import OfficeBrandingProvider
from app.modules.email.factory import (
    ProviderConfig,
    build_email_service,
    build_from_configs,
)
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.protocol import EmailProvider
from app.modules.email.renderer import EmailRenderer
from app.modules.email.sender import TemplatedEmailSender
from app.modules.email_settings.configs import profile_to_config
from app.modules.email_settings.repository import EmailProfileRepository

logger = logging.getLogger(__name__)

EmailService = FailoverEmailService | FakeEmailService


class EmailServiceCache:
    """Cadeia de provedores montada uma vez e remontada quando os perfis
    salvos pela tela mudam.

    A cada ``get()`` lê só ``(id, version)`` dos perfis ativos; se a tupla
    mudou desde a última montagem, remonta. Como a comparação é com o banco,
    a API e o scheduler (processos separados) percebem a troca sozinhos, sem
    reiniciar. Sem perfil ativo no banco (ou sem a tabela), usa o ``.env``.
    """

    def __init__(
        self, session_factory: Callable[[], Session], settings: Settings
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._lock = threading.Lock()
        self._key: tuple | None = None
        self._service: EmailService | None = None

    def get(self) -> EmailService:
        try:
            with self._session_factory() as db:
                repo = EmailProfileRepository(db)
                key = repo.active_versions()
                if self._service is not None and key == self._key:
                    return self._service
                with self._lock:
                    if self._service is None or key != self._key:
                        self._service = self._build(repo.list_active())
                        self._key = key
                return self._service
        except SQLAlchemyError:
            logger.exception("Could not read email profiles, using current chain")
            with self._lock:
                if self._service is None:
                    self._service = build_email_service(self._settings)
                return self._service

    def _build(self, profiles: list) -> EmailService:
        configs: list[ProviderConfig] = []
        for profile in profiles:
            try:
                configs.append(profile_to_config(profile, self._settings))
            except Exception:  # noqa: BLE001 - um perfil ruim não derruba o outro
                logger.exception("Email profile %s skipped", profile.id)
        if configs:
            logger.info(
                "Email chain rebuilt from saved profiles: %s",
                [type(c).__name__ for c in configs],
            )
            return build_from_configs(configs)
        return build_email_service(self._settings)


@lru_cache(maxsize=1)
def _email_service_cache() -> EmailServiceCache:
    return EmailServiceCache(SessionLocal, get_settings())


def get_email_service() -> EmailService:
    return _email_service_cache().get()


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
    """Para quem roda fora de uma requisição (jobs do scheduler, scripts).
    Cada chamada confere a versão dos perfis, então cada lote do scheduler
    já sai pela configuração mais nova."""
    return TemplatedEmailSender(get_email_renderer(), get_email_service())
