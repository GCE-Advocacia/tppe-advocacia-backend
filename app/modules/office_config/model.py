from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base_model import Base


class OfficeConfig(Base):
    __tablename__ = "office_config"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    office_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(18), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    whatsapp_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    hero_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hero_subtitle: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    hero_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hero_image_position: Mapped[str | None] = mapped_column(String(20), nullable=True)

    about_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    about_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    about_image_url: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    about_image_position: Mapped[str | None] = mapped_column(String(20), nullable=True)

    lawyer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lawyer_oab: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lawyer_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lawyer_image_url: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    lawyer_image_position: Mapped[str | None] = mapped_column(String(20), nullable=True)

    differentials: Mapped[list | None] = mapped_column(JSON, nullable=True)
    areas_of_practice: Mapped[list | None] = mapped_column(JSON, nullable=True)

    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_bg_primary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_bg_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_bg_sobre: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_buttons: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_title_primary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_title_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # TODO: add updated_by field to track which user last updated
    # TODO: add updated_at field to track which user last updated
