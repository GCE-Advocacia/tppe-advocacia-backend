from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.email_settings.model import PRIMARY, EmailIdentity, EmailProfile


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
        """``(id, version)`` da conta própria ativa: consulta barata que diz se
        a cadeia de provedores montada em memória ainda vale."""
        rows = self.db.execute(
            select(EmailProfile.id, EmailProfile.version)
            .where(
                EmailProfile.is_active.is_(True),
                EmailProfile.priority == PRIMARY,
                EmailProfile.provider == "smtp",
            )
            .order_by(EmailProfile.priority)
        ).all()
        return tuple((row.id, row.version) for row in rows)

    def get_own_account(self) -> EmailProfile | None:
        """Conta própria em uso: perfil primário, ativo e SMTP."""
        return self.db.scalars(
            select(EmailProfile).where(
                EmailProfile.priority == PRIMARY,
                EmailProfile.is_active.is_(True),
                EmailProfile.provider == "smtp",
            )
        ).first()

    def get_primary(self) -> EmailProfile | None:
        return self.db.scalars(
            select(EmailProfile).where(EmailProfile.priority == PRIMARY)
        ).first()

    def get_identity(self) -> EmailIdentity | None:
        return self.db.get(EmailIdentity, 1)

    def get_identity_for_update(self) -> EmailIdentity:
        identity = self.db.scalars(
            select(EmailIdentity)
            .where(EmailIdentity.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if identity is None:
            identity = EmailIdentity(id=1, version=1)
            self.db.add(identity)
            self.db.flush()
        return identity

    def identity_version(self) -> int:
        return (
            self.db.scalar(select(EmailIdentity.version).where(EmailIdentity.id == 1))
            or 0
        )

    def get_by_id(self, profile_id: int) -> EmailProfile | None:
        return self.db.get(EmailProfile, profile_id)

    def get_for_update(self, profile_id: int) -> EmailProfile | None:
        return self.db.scalars(
            select(EmailProfile)
            .where(EmailProfile.id == profile_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()

    def update_identity(self, identity: EmailIdentity, data: dict) -> EmailIdentity:
        for key, value in data.items():
            setattr(identity, key, value)
        self.db.flush()
        return identity

    def update(self, profile: EmailProfile, data: dict) -> EmailProfile:
        for key, value in data.items():
            setattr(profile, key, value)
        self.db.flush()
        return profile
