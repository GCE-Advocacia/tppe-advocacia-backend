from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base_model import Base

PRIMARY = 1
FALLBACK = 2


class EmailProfile(Base):
    """Perfil de envio salvo pela tela. ``priority`` 1 é o primário e 2 o
    reserva; a migration já cria os dois, desativados.

    ``version`` sobe a cada alteração: serve para recusar quem salva por cima
    de uma edição mais nova (409) e para a API e o scheduler perceberem que
    precisam remontar a cadeia de provedores.
    """

    __tablename__ = "email_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="smtp")
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    security: Mapped[str] = mapped_column(
        String(20), nullable=False, default="starttls"
    )
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Senha do SMTP ou API key do Resend, criptografada com TokenCipher.
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
