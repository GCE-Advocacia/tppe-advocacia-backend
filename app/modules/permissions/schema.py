from pydantic import BaseModel, ConfigDict


class PermissionRead(BaseModel):
    key: str
    name: str
    description: str | None
    sort_order: int

    model_config = ConfigDict(from_attributes=True)
