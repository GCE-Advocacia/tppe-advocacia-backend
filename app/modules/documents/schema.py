from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class ProcessDocumentRead(BaseModel):
    id: int
    process_id: int
    original_name: str
    mime_type: str
    size_bytes: int
    uploaded_by: int | None
    uploaded_by_name: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def resolve_uploader_name(cls, data: object) -> object:
        if isinstance(data, dict):
            return data
        return {
            "id": data.id,
            "process_id": data.process_id,
            "original_name": data.original_name,
            "mime_type": data.mime_type,
            "size_bytes": data.size_bytes,
            "uploaded_by": data.uploaded_by,
            "uploaded_by_name": data.uploader.name if data.uploader else None,
            "created_at": data.created_at,
        }
