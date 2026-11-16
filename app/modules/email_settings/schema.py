from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.email_settings.presets import PresetId

# O Resend continua possível na conta do sistema (.env), mas não aparece
# para o escritório.
Provider = Literal["smtp"]
Security = Literal["starttls", "ssl", "none"]
Account = Literal["own", "system"]


class EmailProfileRead(BaseModel):
    """Nunca devolve o segredo: só ``has_secret``."""

    id: int
    name: str
    priority: int
    provider: str
    preset: str | None
    host: str | None
    port: int | None
    security: Security
    username: str | None
    has_secret: bool
    from_email: str | None
    from_name: str | None
    reply_to: str | None
    is_active: bool
    last_tested_at: datetime | None
    last_test_ok: bool | None
    version: int
    updated_by: int | None
    updated_at: datetime
    # Avisos que não impedem salvar (ex.: remetente de outra conta).
    warnings: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class EmailProfileForm(BaseModel):
    """O que a tela manda, tanto para testar quanto para salvar.

    ``secret`` vazio ou ausente mantém o segredo já salvo.
    """

    model_config = ConfigDict(extra="forbid")

    provider: Provider = "smtp"
    # Provedor da lista: preenche host, porta e segurança. "other" = campos livres.
    preset: PresetId = "other"
    host: str | None = Field(None, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    security: Security = "starttls"
    username: str | None = Field(None, max_length=255)
    secret: str | None = Field(None, max_length=1000)
    from_email: EmailStr | None = None
    from_name: str | None = Field(None, max_length=255)
    reply_to: EmailStr | None = None
    is_active: bool = True

    @field_validator(
        "host", "username", "from_name", "from_email", "reply_to", mode="before"
    )
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value


class EmailProfileUpdate(EmailProfileForm):
    name: str | None = Field(None, min_length=1, max_length=100)
    # Versão que a tela carregou; diferente da do banco = 409.
    version: int = Field(..., ge=1)


class ConnectionStepRead(BaseModel):
    step: Literal["connect", "ehlo", "tls", "auth"]
    ok: bool
    duration_ms: int
    error: str | None = None
    hint: str | None = None


class ConnectionTestRead(BaseModel):
    ok: bool
    steps: list[ConnectionStepRead]


class TestSendRequest(BaseModel):
    to: EmailStr


class TestSendRead(BaseModel):
    provider: str
    message_id: str
    duration_ms: int


class EmailIdentityRead(BaseModel):
    from_name: str | None
    reply_to: str | None
    version: int
    updated_at: datetime | None


class EmailIdentityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_name: str | None = Field(None, max_length=255)
    reply_to: EmailStr | None = None
    version: int = Field(..., ge=1)

    @field_validator("from_name", "reply_to", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value


class ProviderPresetRead(BaseModel):
    id: str
    name: str
    host: str | None
    port: int | None
    security: Security
    password_help: str
    help_url: str | None
    sender_must_match: bool


class EmailStatusRead(BaseModel):
    """Bloco "Status" da tela: tudo em linguagem simples."""

    state: Literal["ok", "degraded", "down"]
    message: str
    account: Account
    account_email: str | None
    own_account_configured: bool
    own_account_error: str | None
    last_sent_at: datetime | None
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_error: str | None


class EmailOverviewRead(BaseModel):
    identity: EmailIdentityRead
    own_account: EmailProfileRead | None
    system_account_email: str | None
    system_account_configured: bool


class TestSendMeRead(BaseModel):
    to: str
    account: Account
    fallback_used: bool
    duration_ms: int
