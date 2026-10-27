from app.modules.permissions.model import Permission
from app.modules.permissions.repository import PermissionRepository


class PermissionService:
    def __init__(self, repository: PermissionRepository) -> None:
        self.repository = repository

    def list_permissions(self) -> list[Permission]:
        return self.repository.list_all()
