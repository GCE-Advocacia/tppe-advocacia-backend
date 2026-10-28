from pydantic import BaseModel


class GoogleDriveStatusRead(BaseModel):
    connected: bool
    email: str | None = None


class GoogleDriveAuthUrlRead(BaseModel):
    auth_url: str
