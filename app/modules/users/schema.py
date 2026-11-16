from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.permissions.model import Permission
from app.shared.types import PermissionKey, Role


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


class UserRead(BaseModel):
    id: int
    name: str
    email: str
    role: Role
    is_active: bool
    permissions: list[str]
    created_by: int | None
    updated_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("permissions", mode="before")
    @classmethod
    def keys_from_permissions(cls, permissions: list[Permission | str]) -> list[str]:
        return [p.key if isinstance(p, Permission) else p for p in permissions]
