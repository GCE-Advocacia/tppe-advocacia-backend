from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.google_drive.model import GoogleDriveConnection, ProcessDriveFolder


class GoogleDriveConnectionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self) -> GoogleDriveConnection | None:
        return self.db.scalars(select(GoogleDriveConnection)).first()

    def save(
        self, encrypted_refresh_token: str, email: str | None, connected_by: int
    ) -> GoogleDriveConnection:
        # Uma única conexão por escritório: conectar de novo substitui a anterior.
        self.delete()
        connection = GoogleDriveConnection(
            encrypted_refresh_token=encrypted_refresh_token,
            email=email,
            connected_by=connected_by,
        )
        self.db.add(connection)
        self.db.flush()
        return connection

    def set_root_folder(self, folder_id: str) -> None:
        connection = self.get()
        if connection is not None:
            connection.root_folder_id = folder_id
            self.db.flush()

    def delete(self) -> None:
        self.db.execute(delete(GoogleDriveConnection))
        self.db.flush()


class ProcessDriveFolderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_folder_id(self, process_id: int) -> str | None:
        return self.db.scalars(
            select(ProcessDriveFolder.folder_id).where(
                ProcessDriveFolder.process_id == process_id
            )
        ).first()

    def set_folder_id(self, process_id: int, folder_id: str) -> None:
        folder = self.db.scalars(
            select(ProcessDriveFolder).where(
                ProcessDriveFolder.process_id == process_id
            )
        ).first()
        if folder is None:
            self.db.add(ProcessDriveFolder(process_id=process_id, folder_id=folder_id))
        else:
            folder.folder_id = folder_id
        self.db.flush()
