from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.modules.office_config.repository import OfficeConfigRepository, ThemeRepository
from app.modules.office_config.service import OfficeConfigService, ThemeService


def get_office_config_service(db: Session = Depends(get_db)) -> OfficeConfigService:
    return OfficeConfigService(OfficeConfigRepository(db))


def get_theme_service(db: Session = Depends(get_db)) -> ThemeService:
    return ThemeService(ThemeRepository(db), OfficeConfigRepository(db))
