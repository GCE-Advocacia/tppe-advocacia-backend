from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.modules.permissions.repository import PermissionRepository
from app.modules.permissions.service import PermissionService


def get_permission_service(db: Session = Depends(get_db)) -> PermissionService:
    return PermissionService(PermissionRepository(db))
