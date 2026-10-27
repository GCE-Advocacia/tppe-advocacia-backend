import pytest

from app.config.settings import Settings
from app.modules.email.factory import build_email_service
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService


def _settings(**env) -> Settings:
    base = {
        "JWT_SECRET_KEY": "x" * 40,
        "APP_ENV": "development",
        "EMAIL_PROVIDERS": "",
        "SMTP_HOST": "",
        "SMTP_FROM_EMAIL": "",
        "RESEND_API_KEY": "",
    }
    base.update(env)
    return Settings(_env_file=None, **base)


def test_no_providers_uses_fake():
    assert isinstance(build_email_service(_settings()), FakeEmailService)


def test_smtp_then_resend():
    service = build_email_service(
        _settings(
            EMAIL_PROVIDERS="smtp, resend",
            SMTP_HOST="smtp.gmail.com",
            SMTP_FROM_EMAIL="conta@gmail.com",
            RESEND_API_KEY="re_123",
        )
    )
    assert isinstance(service, FailoverEmailService)
    assert service.provider_names == ["smtp", "resend"]


def test_resend_without_key_is_skipped():
    service = build_email_service(
        _settings(
            EMAIL_PROVIDERS="smtp,resend",
            SMTP_HOST="smtp.gmail.com",
            SMTP_FROM_EMAIL="conta@gmail.com",
        )
    )
    assert service.provider_names == ["smtp"]


def test_production_falls_back_to_resend_for_old_deploys():
    service = build_email_service(
        _settings(APP_ENV="production", RESEND_API_KEY="re_123")
    )
    assert service.provider_names == ["resend"]


def test_production_without_any_provider_fails():
    with pytest.raises(RuntimeError):
        build_email_service(_settings(APP_ENV="production"))


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        _settings(EMAIL_PROVIDERS="smtp,sendgrid")
