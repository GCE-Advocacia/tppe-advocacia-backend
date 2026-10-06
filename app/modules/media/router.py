from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse

from app.modules.media.deps import get_media_service
from app.modules.media.schema import MediaUploadResponse
from app.modules.media.service import MediaService
from app.modules.media.storage.logo import LogoStorage
from app.modules.users.model import User
from app.shared.deps.auth import get_current_user
from app.shared.http.responses import SuccessResponse, error_responses, ok

router = APIRouter(prefix="/media", tags=["Media"])


@router.get(
    "/logos/{filename}",
    responses=error_responses(404),
    summary="Serve uma logo otimizada",
)
def serve_logo(filename: str) -> FileResponse:
    return FileResponse(LogoStorage().get_file_path(filename), media_type="image/png")


@router.post(
    "/upload",
    status_code=201,
    response_model=SuccessResponse[MediaUploadResponse],
    responses=error_responses(401, 413, 415, 422),
    summary="Carrega um arquivo de imagem",
)
def upload_file(
    request: Request,
    file: UploadFile,
    service: MediaService = Depends(get_media_service),
    _: User = Depends(get_current_user),
) -> SuccessResponse[MediaUploadResponse]:
    return ok(service.upload(file, str(request.base_url)))


@router.get(
    "/{filename}",
    responses=error_responses(404),
    summary="Serve um arquivo enviado",
)
def serve_file(
    filename: str,
    service: MediaService = Depends(get_media_service),
) -> FileResponse:
    path = service.get_file_path(filename)
    return FileResponse(path)
