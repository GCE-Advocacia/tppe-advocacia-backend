from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base_model import Base


class GoogleCredential(Base):
    """Credencial OAuth do Google de um usuário (relação 1:1 com User).

    Guarda apenas o refresh_token, criptografado (Fernet). O access_token é
    de curta duração e obtido sob demanda a partir do refresh_token.
    """

    __tablename__ = "google_credential"
    __table_args__ = (UniqueConstraint("user_id", name="uq_google_credential_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Token de sync incremental do Google (events.list). Null = nunca sincronizou
    # do Google para o sistema; a próxima leitura faz full sync.
    sync_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
