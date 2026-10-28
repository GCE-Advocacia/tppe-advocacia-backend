from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.processes.model import Process
from app.modules.users.model import User
from app.shared.db.base_model import Base


class ExternalApiProvider(str, Enum):
    DATAJUD = "DATAJUD"
    GOOGLE_DRIVE = "GOOGLE_DRIVE"


class ExternalApiOperation(str, Enum):
    PROCESS_MOVEMENT_SYNC = "PROCESS_MOVEMENT_SYNC"
    DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"
    DOCUMENT_DOWNLOAD = "DOCUMENT_DOWNLOAD"
    DOCUMENT_DELETE = "DOCUMENT_DELETE"
    OAUTH = "OAUTH"


class ExternalApiStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class ExternalApiLog(Base):
    __tablename__ = "external_api_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    provider: Mapped[ExternalApiProvider] = mapped_column(
        SAEnum(ExternalApiProvider, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    operation: Mapped[ExternalApiOperation] = mapped_column(
        SAEnum(ExternalApiOperation, native_enum=False, length=40),
        nullable=False,
        index=True,
    )
    status: Mapped[ExternalApiStatus] = mapped_column(
        SAEnum(ExternalApiStatus, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    process_id: Mapped[int | None] = mapped_column(
        ForeignKey("processes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tribunal_alias: Mapped[str | None] = mapped_column(String(30), nullable=True)
    request_identifier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_external_api_logs_created_by"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    process: Mapped[Process | None] = relationship("Process")
    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by])
