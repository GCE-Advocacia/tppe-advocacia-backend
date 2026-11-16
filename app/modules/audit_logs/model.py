import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base_model import Base


class AuditAction(enum.Enum):
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    CLIENT_ANONYMIZED = "CLIENT_ANONYMIZED"
    EMAIL_SETTINGS_UPDATED = "EMAIL_SETTINGS_UPDATED"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    performed_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performed_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_user_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Detalhes livres da ação (ex.: diff dos campos alterados, sem segredos).
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
