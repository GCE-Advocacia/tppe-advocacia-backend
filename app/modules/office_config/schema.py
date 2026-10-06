from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class ListItem(BaseModel):
    title: str = Field(max_length=200)
    description: str = Field(max_length=1000)


_ListField = Annotated[list[ListItem], Field(max_length=50)]


class OfficeConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    office_name: str | None = Field(None, max_length=255)
    cnpj: str | None = Field(None, max_length=18)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    instagram_url: AnyHttpUrl | None = Field(None, max_length=500)
    linkedin_url: AnyHttpUrl | None = Field(None, max_length=500)
    whatsapp_url: AnyHttpUrl | None = Field(None, max_length=500)
    website_url: AnyHttpUrl | None = Field(None, max_length=500)

    hero_title: str | None = Field(None, max_length=255)
    hero_subtitle: str | None = Field(None, max_length=1000)
    hero_image_url: AnyHttpUrl | None = Field(None, max_length=500)
    hero_image_position: str | None = Field(None, max_length=20)

    about_title: str | None = Field(None, max_length=255)
    about_description: str | None = Field(None, max_length=5000)
    about_image_url: AnyHttpUrl | None = Field(None, max_length=500)
    about_image_position: str | None = Field(None, max_length=20)

    lawyer_name: str | None = Field(None, max_length=255)
    lawyer_oab: str | None = Field(None, max_length=50)
    lawyer_description: str | None = Field(None, max_length=5000)
    lawyer_image_url: AnyHttpUrl | None = Field(None, max_length=500)
    lawyer_image_position: str | None = Field(None, max_length=20)

    differentials: _ListField | None = None
    areas_of_practice: _ListField | None = None

    color: str | None = Field(None, max_length=50)
    color_bg_primary: str | None = Field(None, max_length=50)
    color_bg_secondary: str | None = Field(None, max_length=50)
    color_bg_sobre: str | None = Field(None, max_length=50)
    color_buttons: str | None = Field(None, max_length=50)
    color_buttons_hover: str | None = Field(None, max_length=50)
    color_buttons_text: str | None = Field(None, max_length=50)
    color_title_primary: str | None = Field(None, max_length=50)
    color_title_secondary: str | None = Field(None, max_length=50)
    color_text_primary: str | None = Field(None, max_length=50)
    color_text_secondary: str | None = Field(None, max_length=50)
    color_link_primary: str | None = Field(None, max_length=50)
    color_link_secondary: str | None = Field(None, max_length=50)
    theme_id: int | None = None


class OfficeConfigRead(BaseModel):
    id: int

    office_name: str | None
    logo_url: str | None = None
    logo_dark_url: str | None = None
    system_logo_url: str | None = None
    system_logo_dark_url: str | None = None
    favicon_url: str | None = None
    default_logo_url: str | None = None
    default_logo_dark_url: str | None = None
    default_system_logo_url: str | None = None
    default_system_logo_dark_url: str | None = None
    default_favicon_url: str | None = None
    logo_same_for_themes: bool = True
    system_logo_same_for_themes: bool = True
    system_uses_landing_logo: bool = True
    cnpj: str | None
    address: str | None
    phone: str | None
    email: str | None
    instagram_url: str | None
    linkedin_url: str | None
    whatsapp_url: str | None
    website_url: str | None

    hero_title: str | None
    hero_subtitle: str | None
    hero_image_url: str | None
    hero_image_position: str | None

    about_title: str | None
    about_description: str | None
    about_image_url: str | None
    about_image_position: str | None

    lawyer_name: str | None
    lawyer_oab: str | None
    lawyer_description: str | None
    lawyer_image_url: str | None
    lawyer_image_position: str | None

    differentials: list[ListItem] = []
    areas_of_practice: list[ListItem] = []

    color: str | None = None
    color_bg_primary: str | None = None
    color_bg_secondary: str | None = None
    color_bg_sobre: str | None = None
    color_buttons: str | None = None
    color_buttons_hover: str | None = None
    color_buttons_text: str | None = None
    color_title_primary: str | None = None
    color_title_secondary: str | None = None
    color_text_primary: str | None = None
    color_text_secondary: str | None = None
    color_link_primary: str | None = None
    color_link_secondary: str | None = None
    theme_id: int | None = None

    @field_validator("differentials", "areas_of_practice", mode="before")
    @classmethod
    def coerce_none_to_list(cls, v: list | None) -> list:
        return v if v is not None else []

    model_config = ConfigDict(from_attributes=True)


class ThemeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    color: str = Field(default="#232C43", max_length=50)
    color_bg_primary: str = Field(max_length=50)
    color_bg_secondary: str = Field(max_length=50)
    color_bg_sobre: str = Field(max_length=50)
    color_buttons: str = Field(max_length=50)
    color_buttons_hover: str = Field(max_length=50)
    color_buttons_text: str = Field(max_length=50)
    color_title_primary: str = Field(max_length=50)
    color_title_secondary: str = Field(max_length=50)
    color_text_primary: str = Field(max_length=50)
    color_text_secondary: str = Field(max_length=50)
    color_link_primary: str = Field(max_length=50)
    color_link_secondary: str = Field(max_length=50)


class ThemeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    color: str | None = Field(None, max_length=50)
    color_bg_primary: str | None = Field(None, max_length=50)
    color_bg_secondary: str | None = Field(None, max_length=50)
    color_bg_sobre: str | None = Field(None, max_length=50)
    color_buttons: str | None = Field(None, max_length=50)
    color_buttons_hover: str | None = Field(None, max_length=50)
    color_buttons_text: str | None = Field(None, max_length=50)
    color_title_primary: str | None = Field(None, max_length=50)
    color_title_secondary: str | None = Field(None, max_length=50)
    color_text_primary: str | None = Field(None, max_length=50)
    color_text_secondary: str | None = Field(None, max_length=50)
    color_link_primary: str | None = Field(None, max_length=50)
    color_link_secondary: str | None = Field(None, max_length=50)


class ThemeRead(BaseModel):
    id: int
    name: str
    description: str | None
    is_predefined: bool

    color: str
    color_bg_primary: str
    color_bg_secondary: str
    color_bg_sobre: str
    color_buttons: str
    color_buttons_hover: str
    color_buttons_text: str
    color_title_primary: str
    color_title_secondary: str
    color_text_primary: str
    color_text_secondary: str
    color_link_primary: str
    color_link_secondary: str

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThemeQuotaRead(BaseModel):
    max_total: int
    max_custom: int
    total_count: int
    custom_count: int
    is_limit_reached: bool


LogoSlot = Literal[
    "landing-light", "landing-dark", "system-light", "system-dark", "favicon"
]


class LogoSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    logo_same_for_themes: bool = True
    system_logo_same_for_themes: bool = True
    system_uses_landing_logo: bool = True
