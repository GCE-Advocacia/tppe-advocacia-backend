from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Provider = Literal["smtp", "resend"]
Security = Literal["starttls", "ssl", "none"]


class EmailProfileRead(BaseModel):
    """Nunca devolve o segredo: só ``has_secret``."""

    id: int
    name: str
    priority: int
    provider: Provider
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

    model_config = ConfigDict(from_attributes=True)


class EmailProfileForm(BaseModel):
    """O que a tela manda, tanto para testar quanto para salvar.

    ``secret`` vazio ou ausente mantém o segredo já salvo.
    """

    model_config = ConfigDict(extra="forbid")

    provider: Provider = "smtp"
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


class ConnectionTestRead(BaseModel):
    ok: bool
    steps: list[ConnectionStepRead]


class TestSendRequest(BaseModel):
    to: EmailStr


class TestSendRead(BaseModel):
    provider: str
    message_id: str
    duration_ms: int
