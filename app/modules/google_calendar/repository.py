from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.google_calendar.model import GoogleCredential


class GoogleCredentialRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user(self, user_id: int) -> GoogleCredential | None:
        return self.db.scalars(
            select(GoogleCredential).where(GoogleCredential.user_id == user_id)
        ).first()

    def list_all(self) -> list[GoogleCredential]:
        """Todas as credenciais conectadas. Usado pelo job de pull."""
        return list(self.db.scalars(select(GoogleCredential)).all())

    def update_sync_token(
        self, credential: GoogleCredential, sync_token: str | None
    ) -> None:
        credential.sync_token = sync_token
        self.db.flush()

    def upsert(
        self, user_id: int, encrypted_refresh_token: str, scope: str | None
    ) -> GoogleCredential:
        credential = self.get_by_user(user_id)
        if credential is None:
            credential = GoogleCredential(
                user_id=user_id,
                encrypted_refresh_token=encrypted_refresh_token,
                scope=scope,
            )
            self.db.add(credential)
        else:
            credential.encrypted_refresh_token = encrypted_refresh_token
            credential.scope = scope
        self.db.flush()
        return credential

    def delete_by_user(self, user_id: int) -> bool:
        credential = self.get_by_user(user_id)
        if credential is None:
            return False
        self.db.delete(credential)
        self.db.flush()
        return True
