from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.shared.security.password import NewPassword
from app.shared.types import Role, UserStatus

InviteStatus = Literal["PENDING", "EXPIRED", "USED", "CANCELLED"]


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None
    can_view_payments: bool | None = None


class InviteSummary(BaseModel):
    """Último convite do usuário, para a listagem do admin."""

    status: InviteStatus
    sent_at: datetime
    expires_at: datetime


class UserRead(BaseModel):
    id: int
    name: str
    email: str
    role: Role
    status: UserStatus
    is_active: bool
    can_view_payments: bool
    created_by: int | None
    updated_by: int | None
    created_at: datetime
    updated_at: datetime
    invite: InviteSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class InvitePublicRead(BaseModel):
    name: str
    email: str


class InviteAccept(BaseModel):
    password: NewPassword
