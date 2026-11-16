"""Converte perfis salvos (ou o formulário da tela) nos configs da Pessoa 1
(``SmtpConfig`` / ``ResendConfig``)."""

from app.config.settings import Settings
from app.modules.email.factory import ProviderConfig
from app.modules.email.resend_provider import ResendConfig
from app.modules.email.smtp_provider import SmtpConfig
from app.modules.email_settings.model import EmailProfile
from app.modules.email_settings.schema import EmailProfileForm
from app.shared.crypto import TokenCipher
from app.shared.exceptions import (
    EmailEncryptionNotConfiguredError,
    EmailProfileIncompleteError,
)


def get_email_cipher(settings: Settings) -> TokenCipher:
    if not settings.email_encryption_keys:
        raise EmailEncryptionNotConfiguredError()
    return TokenCipher(settings.email_encryption_keys)


def decrypt_secret(profile: EmailProfile, settings: Settings) -> str | None:
    if not profile.secret_encrypted:
        return None
    return get_email_cipher(settings).decrypt(profile.secret_encrypted)


def build_config(
    *,
    provider: str,
    host: str | None,
    port: int | None,
    security: str,
    username: str | None,
    secret: str | None,
    from_email: str | None,
    from_name: str | None,
    reply_to: str | None,
    settings: Settings,
) -> ProviderConfig:
    if provider == "resend":
        required = (("secret", secret), ("from_email", from_email))
        missing = [name for name, value in required if not value]
        if missing:
            raise EmailProfileIncompleteError(missing)
        return ResendConfig(
            api_key=secret,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            max_size_mb=settings.email_max_size_mb,
        )

    required = (("host", host), ("port", port), ("from_email", from_email))
    missing = [name for name, value in required if not value]
    if missing:
        raise EmailProfileIncompleteError(missing)
    return SmtpConfig(
        host=host,
        port=port,
        security=security,
        username=username,
        password=secret if username else None,
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        timeout_seconds=settings.smtp_timeout_seconds,
        max_size_mb=settings.email_max_size_mb,
    )


def form_to_config(
    form: EmailProfileForm, stored_secret: str | None, settings: Settings
) -> ProviderConfig:
    """Senha vazia no formulário usa a já salva."""
    return build_config(
        provider=form.provider,
        host=form.host,
        port=form.port,
        security=form.security,
        username=form.username,
        secret=form.secret or stored_secret,
        from_email=form.from_email,
        from_name=form.from_name,
        reply_to=form.reply_to,
        settings=settings,
    )


def profile_to_config(profile: EmailProfile, settings: Settings) -> ProviderConfig:
    return build_config(
        provider=profile.provider,
        host=profile.host,
        port=profile.port,
        security=profile.security,
        username=profile.username,
        secret=decrypt_secret(profile, settings),
        from_email=profile.from_email,
        from_name=profile.from_name,
        reply_to=profile.reply_to,
        settings=settings,
    )
