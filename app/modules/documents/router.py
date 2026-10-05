from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.modules.documents.deps import get_process_document_service
from app.modules.documents.schema import ProcessDocumentRead
from app.modules.documents.service import ProcessDocumentService
from app.modules.users.model import User
from app.shared.deps.auth import get_current_user
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)

router = APIRouter(tags=["Process Documents"])


@router.post(
    "/processes/{process_id}/documents",
    response_model=SuccessResponse[ProcessDocumentRead],
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 413, 415, 422),
    summary="Anexa um documento ao processo",
)
def upload_process_document(
    process_id: int,
    file: UploadFile,
    service: ProcessDocumentService = Depends(get_process_document_service),
    current_user: User = Depends(get_current_user),
) -> SuccessResponse[ProcessDocumentRead]:
    document = service.upload(process_id, file, current_user=current_user)
    return ok(ProcessDocumentRead.model_validate(document))


@router.get(
    "/processes/{process_id}/documents",
    response_model=PaginatedResponse[ProcessDocumentRead],
    responses=error_responses(401, 404),
    summary="Lista os documentos do processo, do mais recente ao mais antigo",
)
def list_process_documents(
    process_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: ProcessDocumentService = Depends(get_process_document_service),
    _: User = Depends(get_current_user),
) -> PaginatedResponse[ProcessDocumentRead]:
    items, total = service.list_documents(process_id, page=page, limit=limit)
    return paginated(
        [ProcessDocumentRead.model_validate(d) for d in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/processes/{process_id}/documents/{document_id}/download",
    response_class=FileResponse,
    responses=error_responses(401, 404),
    summary="Baixa um documento do processo",
)
def download_process_document(
    process_id: int,
    document_id: int,
    service: ProcessDocumentService = Depends(get_process_document_service),
    _: User = Depends(get_current_user),
) -> FileResponse:
    document, path = service.get_download(process_id, document_id)
    return FileResponse(
        path, media_type=document.mime_type, filename=document.original_name
    )


@router.delete(
    "/processes/{process_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
    summary="Exclui um documento (apenas administrador ou quem enviou)",
)
def delete_process_document(
    process_id: int,
    document_id: int,
    service: ProcessDocumentService = Depends(get_process_document_service),
    current_user: User = Depends(get_current_user),
) -> None:
    service.delete(process_id, document_id, current_user=current_user)
