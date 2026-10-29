from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.shared.types import Role


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None
    can_view_payments: bool | None = None


class UserRead(BaseModel):
    id: int
    name: str
    email: str
    role: Role
    is_active: bool
    can_view_payments: bool
    created_by: int | None
    updated_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
