from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base_model import Base
from app.shared.types import Role


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_view_payments: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_users_created_by"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_users_updated_by"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
