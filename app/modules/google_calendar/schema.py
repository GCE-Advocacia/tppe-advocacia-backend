from datetime import datetime

from pydantic import BaseModel


class GoogleAuthUrlRead(BaseModel):
    auth_url: str


class GoogleStatusRead(BaseModel):
    connected: bool
    connected_at: datetime | None = None
    scope: str | None = None


class GooglePullResult(BaseModel):
    """Resultado do pull Google -> sistema."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
