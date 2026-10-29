import pytest
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.documents.model import ProcessDocument
from app.modules.google_drive.repository import (
    GoogleDriveConnectionRepository,
    ProcessDriveFolderRepository,
)
from app.modules.processes.model import Process
from app.modules.processes.repository import ProcessRepository
from app.modules.users.repository import UserRepository
from app.shared.types import Role


@pytest.fixture
def admin_id(db: Session) -> int:
    return (
        UserRepository(db)
        .create(
            name="Admin",
            email="admin-drive@example.test",
            hashed_password="unused",
            role=Role.ADMIN,
        )
        .id
    )


@pytest.fixture
def process(db: Session) -> Process:
    client = ClientRepository(db).create(name="Cliente Drive", cpf="11122233355")
    return ProcessRepository(db).create(
        number="00012345620248260100",
        client_id=client.id,
        court="TJSP",
        action_type="Ação Cível",
    )


def test_save_replaces_previous_connection_and_clears_root(db: Session, admin_id):
    repo = GoogleDriveConnectionRepository(db)
    repo.save("token-1", "um@example.test", admin_id)
    repo.set_root_folder("root-1")
    repo.save("token-2", "dois@example.test", admin_id)
    db.commit()

    connection = repo.get()
    assert connection is not None
    assert connection.encrypted_refresh_token == "token-2"
    assert connection.email == "dois@example.test"
    assert connection.root_folder_id is None
    assert connection.connected_by == admin_id
    assert db.query(type(connection)).count() == 1


def test_get_without_connection_returns_none(db: Session):
    assert GoogleDriveConnectionRepository(db).get() is None


def test_delete_removes_connection(db: Session, admin_id):
    repo = GoogleDriveConnectionRepository(db)
    repo.save("token", None, admin_id)
    repo.delete()
    db.commit()
    assert repo.get() is None


def test_folder_upsert(db: Session, process: Process):
    repo = ProcessDriveFolderRepository(db)
    assert repo.get_folder_id(process.id) is None
    repo.set_folder_id(process.id, "a")
    repo.set_folder_id(process.id, "b")
    db.commit()
    assert repo.get_folder_id(process.id) == "b"


def test_document_storage_defaults_to_local(db: Session, process: Process):
    document = ProcessDocument(
        process_id=process.id,
        original_name="a.pdf",
        stored_name="x.pdf",
        mime_type="application/pdf",
        size_bytes=1,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    assert document.storage == "local"
