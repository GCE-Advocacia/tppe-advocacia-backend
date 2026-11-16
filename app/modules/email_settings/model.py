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
# Antigo perfil reserva: ficou no banco, mas não é mais editável nem usado.
# A reserva agora é sempre a conta do sistema (SMTP do .env).
FALLBACK = 2


class EmailProfile(Base):
    """Conta própria do escritório (``priority`` 1). Desativada, o envio sai
    pela conta do sistema; ativa, a conta do sistema vira a reserva.

    ``version`` sobe a cada alteração: serve para recusar quem salva por cima
    de uma edição mais nova (409) e para a API e o scheduler perceberem que
    precisam remontar a cadeia de provedores.
    """

    __tablename__ = "email_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="smtp")
    # Provedor escolhido na lista (gmail, outlook, ...); "other" = campos livres.
    preset: Mapped[str | None] = mapped_column(String(30), nullable=True)
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


class EmailIdentity(Base):
    """Com que nome e para onde respondem os e-mails do escritório. Vale para
    a conta própria e para a conta do sistema. Linha única (``id`` 1)."""

    __tablename__ = "email_identity"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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
