from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base_model import Base


class Permission(Base):
    """Catálogo das abas da área do sistema (uma linha por aba)."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(nullable=False)


class UserPermission(Base):
    """Abas liberadas para cada usuário."""

    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "permission_id", name="uq_user_permissions_user_permission"
        ),
        Index("ix_user_permissions_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
