from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class ListItem(BaseModel):
    title: str = Field(max_length=200)
    description: str = Field(max_length=1000)


_ListField = Annotated[list[ListItem], Field(max_length=50)]


class OfficeConfigUpdate(BaseModel):
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
    color_title_primary: str | None = Field(None, max_length=50)
    color_title_secondary: str | None = Field(None, max_length=50)
    color_text_primary: str | None = Field(None, max_length=50)
    color_text_secondary: str | None = Field(None, max_length=50)
    color_link_primary: str | None = Field(None, max_length=50)
    color_link_secondary: str | None = Field(None, max_length=50)


class OfficeConfigRead(BaseModel):
    id: int

    office_name: str | None
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
    color_title_primary: str | None = None
    color_title_secondary: str | None = None
    color_text_primary: str | None = None
    color_text_secondary: str | None = None
    color_link_primary: str | None = None
    color_link_secondary: str | None = None

    @field_validator("differentials", "areas_of_practice", mode="before")
    @classmethod
    def coerce_none_to_list(cls, v: list | None) -> list:
        return v if v is not None else []

    model_config = ConfigDict(from_attributes=True)
