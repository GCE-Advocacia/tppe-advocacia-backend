from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.email_settings.model import EmailProfile


class EmailProfileRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> list[EmailProfile]:
        return list(
            self.db.scalars(select(EmailProfile).order_by(EmailProfile.priority)).all()
        )

    def list_active(self) -> list[EmailProfile]:
        return list(
            self.db.scalars(
                select(EmailProfile)
                .where(EmailProfile.is_active.is_(True))
                .order_by(EmailProfile.priority)
            ).all()
        )

    def active_versions(self) -> tuple[tuple[int, int], ...]:
        """``(id, version)`` dos perfis ativos: consulta barata que diz se a
        cadeia de provedores montada em memória ainda vale."""
        rows = self.db.execute(
            select(EmailProfile.id, EmailProfile.version)
            .where(EmailProfile.is_active.is_(True))
            .order_by(EmailProfile.priority)
        ).all()
        return tuple((row.id, row.version) for row in rows)

    def get_by_id(self, profile_id: int) -> EmailProfile | None:
        return self.db.get(EmailProfile, profile_id)

    def get_for_update(self, profile_id: int) -> EmailProfile | None:
        return self.db.scalars(
            select(EmailProfile)
            .where(EmailProfile.id == profile_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()

    def update(self, profile: EmailProfile, data: dict) -> EmailProfile:
        for key, value in data.items():
            setattr(profile, key, value)
        self.db.flush()
        return profile
