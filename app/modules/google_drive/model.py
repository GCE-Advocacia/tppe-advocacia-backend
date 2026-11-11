from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.processes.model import Process  # noqa: F401  (registra a FK)
from app.modules.users.model import User  # noqa: F401  (registra a FK)
from app.shared.db.base_model import Base


class GoogleDriveConnection(Base):
    """Conexão única do escritório com o Google Drive.

    Guarda só o refresh_token, criptografado (Fernet), como no Google Calendar.
    """

    __tablename__ = "google_drive_connection"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    root_folder_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    connected_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_google_drive_connection_connected_by",
        ),
        nullable=True,
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProcessDriveFolder(Base):
    __tablename__ = "process_drive_folders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey(
            "processes.id",
            ondelete="CASCADE",
            name="fk_process_drive_folders_process_id",
        ),
        nullable=False,
        unique=True,
    )
    folder_id: Mapped[str] = mapped_column(String(128), nullable=False)
