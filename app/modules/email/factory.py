"""Monta a cadeia de provedores de e-mail a partir da configuração."""

import logging
from dataclasses import dataclass, replace

from app.config.settings import Settings
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.protocol import EmailProvider
from app.modules.email.resend_provider import ResendConfig, ResendProvider
from app.modules.email.smtp_provider import SmtpConfig, SmtpProvider

logger = logging.getLogger(__name__)

ProviderConfig = SmtpConfig | ResendConfig


# Nomes no histórico e no circuit breaker.
OWN_ACCOUNT = "own"
SYSTEM_ACCOUNT = "system"


@dataclass(frozen=True)
class SenderIdentity:
    """Nome do remetente e responder para do escritório (vale para as duas contas)."""

    from_name: str | None = None
    reply_to: str | None = None


def build_provider(config: ProviderConfig, name: str | None = None) -> EmailProvider:
    if isinstance(config, SmtpConfig):
        return SmtpProvider(config, name or "smtp")
    return ResendProvider(config, name or "resend")


def with_identity(
    config: ProviderConfig, identity: SenderIdentity | None
) -> ProviderConfig:
    if identity is None:
        return config
    return replace(
        config,
        from_name=identity.from_name or config.from_name,
        reply_to=identity.reply_to or config.reply_to,
    )


def system_providers(
    settings: Settings, identity: SenderIdentity | None = None
) -> list[EmailProvider]:
    """Conta do sistema (SMTP do ``.env``), com a identidade do escritório."""
    providers: list[EmailProvider] = []
    for index, config in enumerate(configs_from_settings(settings)):
        name = SYSTEM_ACCOUNT if index == 0 else f"{SYSTEM_ACCOUNT}-{index + 1}"
        providers.append(build_provider(with_identity(config, identity), name))
    return providers


def build_from_configs(configs: list[ProviderConfig]) -> FailoverEmailService:
    """Gancho para quem tiver as configs prontas (ex.: perfis salvos no banco)."""
    return FailoverEmailService([build_provider(c) for c in configs])


def configs_from_settings(settings: Settings) -> list[ProviderConfig]:
    names = list(settings.email_providers)
    if not names and settings.app_env == "production" and settings.resend_api_key:
        # Compatibilidade com o deploy antigo, que só tinha RESEND_API_KEY.
        logger.warning("EMAIL_PROVIDERS not set, falling back to resend")
        names = ["resend"]

    configs: list[ProviderConfig] = []
    for name in names:
        if name == "smtp":
            if not settings.smtp_host or not settings.smtp_from_email:
                logger.warning("SMTP skipped: SMTP_HOST or SMTP_FROM_EMAIL not set")
                continue
            configs.append(
                SmtpConfig(
                    host=settings.smtp_host,
                    port=settings.smtp_port,
                    security=settings.smtp_security,
                    username=settings.smtp_username or None,
                    password=settings.smtp_password or None,
                    from_email=settings.smtp_from_email,
                    from_name=settings.smtp_from_name or None,
                    timeout_seconds=settings.smtp_timeout_seconds,
                    max_size_mb=settings.email_max_size_mb,
                )
            )
        elif name == "resend":
            if not settings.resend_api_key:
                logger.warning("Resend skipped: RESEND_API_KEY not set")
                continue
            configs.append(
                ResendConfig(
                    api_key=settings.resend_api_key,
                    from_email=settings.resend_from_email,
                    from_name=settings.smtp_from_name or None,
                    max_size_mb=settings.email_max_size_mb,
                )
            )
    return configs


def build_email_service(
    settings: Settings,
) -> FailoverEmailService | FakeEmailService:
    configs = configs_from_settings(settings)
    if configs:
        return build_from_configs(configs)
    if settings.app_env == "production":
        raise RuntimeError(
            "Nenhum provedor de e-mail configurado. Defina EMAIL_PROVIDERS "
            "e as variáveis SMTP_* (ou RESEND_API_KEY)."
        )
    logger.info("No email provider configured, using FakeEmailService")
    return FakeEmailService()
