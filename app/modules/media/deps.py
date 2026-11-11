from fastapi import Depends

from app.modules.media.service import MediaService
from app.modules.media.storage.object_storage import ObjectStorage, get_object_storage


def get_media_service(
    storage: ObjectStorage = Depends(get_object_storage),
) -> MediaService:
    return MediaService(storage)
