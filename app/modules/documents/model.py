from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.processes.model import Process  # noqa: F401  (registra a FK)
from app.modules.users.model import User
from app.shared.db.base_model import Base


class ProcessDocument(Base):
    __tablename__ = "process_documents"
    __table_args__ = (
        UniqueConstraint("stored_name", name="uq_process_documents_stored_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey(
            "processes.id",
            ondelete="CASCADE",
            name="fk_process_documents_process_id",
        ),
        nullable=False,
        index=True,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_process_documents_uploaded_by",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    uploader: Mapped[User | None] = relationship("User", foreign_keys=[uploaded_by])
