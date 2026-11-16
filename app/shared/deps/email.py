import logging
import threading
from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.db.database import SessionLocal, get_db
from app.modules.email.branding import OfficeBrandingProvider
from app.modules.email.factory import (
    OWN_ACCOUNT,
    ProviderConfig,
    SenderIdentity,
    build_provider,
    system_providers,
    with_identity,
)
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.protocol import EmailProvider
from app.modules.email.renderer import EmailRenderer
from app.modules.email.sender import TemplatedEmailSender
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.sender import QueuedEmailSender
from app.modules.email_outbox.service import EmailOutbox
from app.modules.email_settings.configs import profile_to_config
from app.modules.email_settings.repository import EmailProfileRepository

logger = logging.getLogger(__name__)

EmailService = FailoverEmailService | FakeEmailService


class EmailServiceCache:
    """Cadeia de envio montada uma vez e remontada quando a configuração da
    tela muda: conta própria do escritório (se ativa) e, como reserva fixa,
    a conta do sistema (SMTP do ``.env``). As duas com o nome do remetente e
    o responder para do escritório.

    A cada ``get()`` lê só as versões (perfil ativo e identidade); se
    mudaram desde a última montagem, remonta. Como a comparação é com o
    banco, a API e o scheduler percebem a troca sozinhos, sem reiniciar.
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
                key = (repo.active_versions(), repo.identity_version())
                if self._service is not None and key == self._key:
                    return self._service
                with self._lock:
                    if self._service is None or key != self._key:
                        self._service = self._build(repo)
                        self._key = key
                return self._service
        except SQLAlchemyError:
            logger.exception("Could not read email settings, using current chain")
            with self._lock:
                if self._service is None:
                    self._service = build_chain(None, None, self._settings)
                return self._service

    def _build(self, repo: EmailProfileRepository) -> EmailService:
        identity = repo.get_identity()
        sender = (
            SenderIdentity(identity.from_name, identity.reply_to)
            if identity is not None
            else None
        )
        own = repo.get_own_account()
        own_config: ProviderConfig | None = None
        if own is not None:
            try:
                own_config = profile_to_config(own, self._settings)
            except Exception:  # noqa: BLE001 - conta própria ruim não derruba o envio
                logger.exception("Own email account skipped")
        service = build_chain(own_config, sender, self._settings)
        logger.info(
            "Email chain rebuilt: %s",
            getattr(service, "provider_names", [type(service).__name__]),
        )
        return service


def build_chain(
    own: ProviderConfig | None,
    sender: SenderIdentity | None,
    settings: Settings,
) -> EmailService:
    """Conta própria primeiro; a conta do sistema é sempre a reserva."""
    providers: list[EmailProvider] = []
    if own is not None:
        providers.append(build_provider(with_identity(own, sender), OWN_ACCOUNT))
    providers += system_providers(settings, sender)
    if providers:
        return FailoverEmailService(providers)
    if settings.app_env == "production":
        raise RuntimeError(
            "Nenhuma conta de e-mail configurada. Defina EMAIL_PROVIDERS e as "
            "variáveis SMTP_* (conta do sistema)."
        )
    logger.info("No email provider configured, using FakeEmailService")
    return FakeEmailService()


@lru_cache(maxsize=1)
def _email_service_cache() -> EmailServiceCache:
    return EmailServiceCache(SessionLocal, get_settings())


def get_email_service() -> EmailService:
    return _email_service_cache().get()


@lru_cache(maxsize=1)
def get_email_renderer() -> EmailRenderer:
    settings = get_settings()
    return EmailRenderer(
        OfficeBrandingProvider(
            SessionLocal, fallback_name=settings.smtp_from_name or None
        ),
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


def get_queued_sender(db: Session = Depends(get_db)) -> QueuedEmailSender:
    """Remetente das rotas: grava na fila; quem entrega é o worker."""
    return QueuedEmailSender(EmailOutbox(EmailOutboxRepository(db)))


def build_queued_sender(db: Session) -> QueuedEmailSender:
    """Mesmo remetente para os jobs do scheduler, na sessão do job."""
    return QueuedEmailSender(EmailOutbox(EmailOutboxRepository(db)))
