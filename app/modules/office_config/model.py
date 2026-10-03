from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
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
    color_buttons_hover: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_buttons_text: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_title_primary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_title_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_text_primary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_text_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_link_primary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_link_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)
    theme_id: Mapped[int | None] = mapped_column(
        ForeignKey("landing_page_themes.id", ondelete="SET NULL"), nullable=True
    )

    # TODO: add updated_by field to track which user last updated
    # TODO: add updated_at field to track which user last updated


class LandingPageTheme(Base):
    __tablename__ = "landing_page_themes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_predefined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    color: Mapped[str] = mapped_column(String(50), nullable=False)
    color_bg_primary: Mapped[str] = mapped_column(String(50), nullable=False)
    color_bg_secondary: Mapped[str] = mapped_column(String(50), nullable=False)
    color_bg_sobre: Mapped[str] = mapped_column(String(50), nullable=False)
    color_buttons: Mapped[str] = mapped_column(String(50), nullable=False)
    color_buttons_hover: Mapped[str] = mapped_column(String(50), nullable=False)
    color_buttons_text: Mapped[str] = mapped_column(String(50), nullable=False)
    color_title_primary: Mapped[str] = mapped_column(String(50), nullable=False)
    color_title_secondary: Mapped[str] = mapped_column(String(50), nullable=False)
    color_text_primary: Mapped[str] = mapped_column(String(50), nullable=False)
    color_text_secondary: Mapped[str] = mapped_column(String(50), nullable=False)
    color_link_primary: Mapped[str] = mapped_column(String(50), nullable=False)
    color_link_secondary: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
