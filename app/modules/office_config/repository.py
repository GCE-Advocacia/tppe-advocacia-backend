from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.office_config.model import LandingPageTheme, OfficeConfig


class OfficeConfigRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_config(self) -> OfficeConfig:
        return self.db.scalars(select(OfficeConfig).where(OfficeConfig.id == 1)).one()

    def update_config(self, data: dict) -> OfficeConfig:
        config = self.get_config()
        for key, value in data.items():
            setattr(config, key, value)
        self.db.flush()
        return config


class ThemeRepository:
    """Repositório de temas da landing page."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_themes(self) -> list[LandingPageTheme]:
        return list(
            self.db.scalars(
                select(LandingPageTheme).order_by(
                    LandingPageTheme.is_predefined.desc(), LandingPageTheme.id.asc()
                )
            ).all()
        )

    def get_by_id(self, theme_id: int) -> LandingPageTheme | None:
        return self.db.scalars(
            select(LandingPageTheme).where(LandingPageTheme.id == theme_id)
        ).first()

    def count_themes(self) -> int:
        return self.db.scalar(select(func.count(LandingPageTheme.id))) or 0

    def count_custom_themes(self) -> int:
        return (
            self.db.scalar(
                select(func.count(LandingPageTheme.id)).where(
                    LandingPageTheme.is_predefined.is_(False)
                )
            )
            or 0
        )

    def create_theme(self, data: dict) -> LandingPageTheme:
        theme = LandingPageTheme(**data)
        self.db.add(theme)
        self.db.flush()
        return theme

    def update_theme(self, theme: LandingPageTheme, data: dict) -> LandingPageTheme:
        for key, value in data.items():
            setattr(theme, key, value)
        self.db.flush()
        return theme

    def delete_theme(self, theme: LandingPageTheme) -> None:
        self.db.delete(theme)
        self.db.flush()
