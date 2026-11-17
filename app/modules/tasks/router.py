from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.config.settings import Settings, get_settings
from app.modules.tasks.deps import get_task_service
from app.modules.tasks.model import TaskPriority, TaskStatus
from app.modules.tasks.schema import (
    KanbanColumn,
    KanbanRead,
    TaskCreate,
    TaskMove,
    TaskRead,
    TaskUpdate,
)
from app.modules.tasks.service import TaskService
from app.modules.users.model import User
from app.shared.deps.auth import require_any_permission, require_permission
from app.shared.http.responses import (
    PaginatedResponse,
    SuccessResponse,
    error_responses,
    ok,
    paginated,
)
from app.shared.types import PermissionKey

# A tela de Processos lista, cria, edita e exclui as tarefas do processo (D6).
_tasks_or_processes = require_any_permission(
    PermissionKey.TAREFAS, PermissionKey.PROCESSOS
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[TaskRead],
    responses=error_responses(401, 422),
    summary="Cria uma nova tarefa",
)
def create_task(
    payload: TaskCreate,
    service: TaskService = Depends(get_task_service),
    current_user: User = Depends(_tasks_or_processes),
) -> SuccessResponse[TaskRead]:
    task = service.create_task(payload, created_by=current_user)
    return ok(TaskRead.model_validate(task))


@router.get(
    "",
    response_model=PaginatedResponse[TaskRead],
    responses=error_responses(401),
    summary="Lista tarefas com filtros e paginação",
)
def list_tasks(
    assigned_to: int | None = Query(None),
    status: TaskStatus | None = Query(None),
    priority: TaskPriority | None = Query(None),
    client_id: int | None = Query(None),
    process_id: int | None = Query(None),
    due_date_from: datetime | None = Query(None),
    due_date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: TaskService = Depends(get_task_service),
    _: User = Depends(_tasks_or_processes),
) -> PaginatedResponse[TaskRead]:
    items, total = service.list_tasks(
        assigned_to=assigned_to,
        status=status,
        priority=priority,
        client_id=client_id,
        process_id=process_id,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        page=page,
        limit=limit,
    )
    return paginated(
        [TaskRead.model_validate(t) for t in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/kanban",
    response_model=SuccessResponse[KanbanRead],
    responses=error_responses(401),
    summary="Obtém tarefas agrupadas por status (visualização Kanban)",
)
def get_kanban(
    assigned_to: int | None = Query(None),
    client_id: int | None = Query(None),
    process_id: int | None = Query(None),
    service: TaskService = Depends(get_task_service),
    settings: Settings = Depends(get_settings),
    _: User = Depends(require_permission(PermissionKey.TAREFAS)),
) -> SuccessResponse[KanbanRead]:
    grouped = service.get_kanban_view(
        assigned_to=assigned_to,
        client_id=client_id,
        process_id=process_id,
        max_per_column=settings.kanban_max_per_column,
    )
    columns = {
        status.value: KanbanColumn(
            items=[TaskRead.model_validate(t) for t in items],
            total=total,
            has_more=total > len(items),
        )
        for status, (items, total) in grouped.items()
    }
    return ok(KanbanRead(**columns))


@router.get(
    "/{task_id}",
    response_model=SuccessResponse[TaskRead],
    responses=error_responses(401, 404),
    summary="Obtém uma tarefa por ID",
)
def get_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
    _: User = Depends(require_permission(PermissionKey.TAREFAS)),
) -> SuccessResponse[TaskRead]:
    task = service.get_task(task_id)
    return ok(TaskRead.model_validate(task))


@router.patch(
    "/{task_id}",
    response_model=SuccessResponse[TaskRead],
    responses=error_responses(401, 404, 422),
    summary="Atualiza parcialmente uma tarefa",
)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    service: TaskService = Depends(get_task_service),
    current_user: User = Depends(_tasks_or_processes),
) -> SuccessResponse[TaskRead]:
    task = service.update_task(task_id, payload, updated_by=current_user)
    return ok(TaskRead.model_validate(task))


@router.patch(
    "/{task_id}/move",
    response_model=SuccessResponse[TaskRead],
    responses=error_responses(401, 404, 422),
    summary="Move uma tarefa entre colunas (Kanban) com reordenação atômica",
)
def move_task(
    task_id: int,
    payload: TaskMove,
    service: TaskService = Depends(get_task_service),
    current_user: User = Depends(require_permission(PermissionKey.TAREFAS)),
) -> SuccessResponse[TaskRead]:
    task = service.move_task(task_id, payload, updated_by=current_user)
    return ok(TaskRead.model_validate(task))


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
    summary="Remove uma tarefa (apenas administrador ou criador)",
)
def delete_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
    current_user: User = Depends(_tasks_or_processes),
) -> None:
    service.delete_task(task_id, current_user=current_user)
