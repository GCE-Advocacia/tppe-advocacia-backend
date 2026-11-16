from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.email_outbox.model import EmailStatus
from app.modules.permissions.model import Permission
from app.shared.security.password import NewPassword
from app.shared.types import PermissionKey, Role, UserStatus

InviteStatus = Literal["PENDING", "EXPIRED", "USED", "CANCELLED"]


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    permissions: list[PermissionKey] = Field(default_factory=list)


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None
    permissions: list[PermissionKey] | None = None


class InviteSummary(BaseModel):
    """Último convite do usuário, para a listagem do admin.

    ``sent_at`` é quando o convite foi gerado; ``last_sent_at`` é quando o
    e-mail saiu de fato (nulo enquanto está na fila) e ``email_status`` é a
    situação do e-mail do convite mais recente.
    """

    status: InviteStatus
    sent_at: datetime
    expires_at: datetime
    email_status: EmailStatus | None = None
    last_sent_at: datetime | None = None


class UserRead(BaseModel):
    id: int
    name: str
    email: str
    role: Role
    status: UserStatus
    is_active: bool
    permissions: list[str]
    created_by: int | None
    updated_by: int | None
    created_at: datetime
    updated_at: datetime
    invite: InviteSummary | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("permissions", mode="before")
    @classmethod
    def keys_from_permissions(cls, permissions: list[Permission | str]) -> list[str]:
        return [p.key if isinstance(p, Permission) else p for p in permissions]


class InvitePublicRead(BaseModel):
    name: str
    email: str


class InviteAccept(BaseModel):
    password: NewPassword
