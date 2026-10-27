from typing import Literal

from pydantic import BaseModel

PreviewFormat = Literal["html", "text"]


class EmailTemplateRead(BaseModel):
    id: str
    name: str
    description: str


class EmailTemplatePreviewRead(BaseModel):
    id: str
    format: PreviewFormat
    subject: str
    content: str
