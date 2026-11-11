from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse

from app.modules.media.deps import get_media_service
from app.modules.media.schema import MediaUploadResponse
from app.modules.media.service import MediaService
from app.modules.media.storage.object_storage import (
    CACHE_CONTROL,
    LocalObjectStorage,
    ObjectStorage,
    get_object_storage,
)
from app.modules.users.model import User
from app.shared.deps.auth import get_current_user
from app.shared.exceptions import MediaNotFoundError
from app.shared.http.responses import SuccessResponse, error_responses, ok

router = APIRouter(prefix="/media", tags=["Media"])


@router.post(
    "/upload",
    status_code=201,
    response_model=SuccessResponse[MediaUploadResponse],
    responses=error_responses(401, 413, 415, 422),
    summary="Carrega um arquivo de imagem",
)
def upload_file(
    file: UploadFile,
    service: MediaService = Depends(get_media_service),
    _: User = Depends(get_current_user),
) -> SuccessResponse[MediaUploadResponse]:
    return ok(service.upload(file))


@router.get(
    "/{key:path}",
    responses=error_responses(404),
    summary="Serve uma imagem salva no disco local (apenas em desenvolvimento)",
)
def serve_file(
    key: str,
    storage: ObjectStorage = Depends(get_object_storage),
) -> FileResponse:
    # Com object storage as URLs apontam direto para o bucket; esta rota só
    # existe para o armazenamento local de desenvolvimento.
    if not isinstance(storage, LocalObjectStorage):
        raise MediaNotFoundError()
    return FileResponse(storage.path_for(key), headers={"Cache-Control": CACHE_CONTROL})
