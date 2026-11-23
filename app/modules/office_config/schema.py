from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class ReadListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)

    @field_validator("title", "description", mode="before")
    @classmethod
    def coerce_str(cls, v: object) -> str:
        return "" if v is None else str(v)


class ListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=1000)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("O título não pode ser vazio.")
            return stripped
        return v


_HexColor = Annotated[
    str,
    Field(pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", strict=True),
]


UpdateListItem = ListItem
_DifferentialsField = Annotated[list[ListItem], Field(max_length=3)]
_AreasField = Annotated[list[ListItem], Field(max_length=6)]
_ButtonRadius = Annotated[
    str, Field(max_length=20, pattern=r"^(?:[0-9]|1[0-9]|2[0-4]|999)px$", strict=True)
]


class OfficeConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    button_radius: _ButtonRadius = "6px"
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

    differentials: _DifferentialsField | None = None
    areas_of_practice: _AreasField | None = None

    @field_validator(
        "instagram_url",
        "linkedin_url",
        "whatsapp_url",
        "website_url",
        "hero_image_url",
        "about_image_url",
        "lawyer_image_url",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    color: _HexColor | None = None
    color_bg_primary: _HexColor | None = None
    color_bg_secondary: _HexColor | None = None
    color_bg_sobre: _HexColor | None = None
    color_buttons: _HexColor | None = None
    color_buttons_hover: _HexColor | None = None
    color_buttons_text: _HexColor | None = None
    system_uses_landing_buttons: bool | None = None
    color_buttons_system: _HexColor | None = None
    color_buttons_system_hover: _HexColor | None = None
    color_buttons_system_text: _HexColor | None = None
    color_title_primary: _HexColor | None = None
    color_title_secondary: _HexColor | None = None
    color_text_primary: _HexColor | None = None
    color_text_secondary: _HexColor | None = None
    color_link_primary: _HexColor | None = None
    color_link_secondary: _HexColor | None = None
    theme_id: int | None = None


class OfficeConfigRead(BaseModel):
    id: int
    button_radius: _ButtonRadius = "6px"

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
    system_uses_landing_buttons: bool = True
    color_buttons_system: str | None = None
    color_buttons_system_hover: str | None = None
    color_buttons_system_text: str | None = None
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

    differentials: list[ReadListItem] = []
    areas_of_practice: list[ReadListItem] = []

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


def _strip_theme_name(v: object) -> object:
    if isinstance(v, str):
        stripped = v.strip()
        if not stripped:
            raise ValueError("O nome do tema não pode ser vazio.")
        return stripped
    return v


class ThemeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    color: _HexColor = "#232C43"
    color_bg_primary: _HexColor
    color_bg_secondary: _HexColor
    color_bg_sobre: _HexColor
    color_buttons: _HexColor
    color_buttons_hover: _HexColor
    color_buttons_text: _HexColor
    system_uses_landing_buttons: bool = True
    color_buttons_system: _HexColor | None = None
    color_buttons_system_hover: _HexColor | None = None
    color_buttons_system_text: _HexColor | None = None
    color_title_primary: _HexColor
    color_title_secondary: _HexColor
    color_text_primary: _HexColor
    color_text_secondary: _HexColor
    color_link_primary: _HexColor
    color_link_secondary: _HexColor

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        return _strip_theme_name(v)


class ThemeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    color: _HexColor | None = None
    color_bg_primary: _HexColor | None = None
    color_bg_secondary: _HexColor | None = None
    color_bg_sobre: _HexColor | None = None
    color_buttons: _HexColor | None = None
    color_buttons_hover: _HexColor | None = None
    color_buttons_text: _HexColor | None = None
    system_uses_landing_buttons: bool | None = None
    color_buttons_system: _HexColor | None = None
    color_buttons_system_hover: _HexColor | None = None
    color_buttons_system_text: _HexColor | None = None
    color_title_primary: _HexColor | None = None
    color_title_secondary: _HexColor | None = None
    color_text_primary: _HexColor | None = None
    color_text_secondary: _HexColor | None = None
    color_link_primary: _HexColor | None = None
    color_link_secondary: _HexColor | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if v is None:
            return None
        return _strip_theme_name(v)


class ThemeDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if v is None:
            return None
        return _strip_theme_name(v)


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
    system_uses_landing_buttons: bool = True
    color_buttons_system: str | None = None
    color_buttons_system_hover: str | None = None
    color_buttons_system_text: str | None = None
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
