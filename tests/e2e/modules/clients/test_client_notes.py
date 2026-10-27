import bcrypt
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.clients.model import Client, ClientNote
from app.modules.clients.repository import ClientRepository
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.types import Role

CLIENTS_URL = "/api/v1/clients"


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@pytest.fixture
def created_client_ids(db_session: Session):
    ids: list[int] = []
    yield ids
    if ids:
        db_session.execute(delete(ClientNote).where(ClientNote.client_id.in_(ids)))
        db_session.execute(delete(Client).where(Client.id.in_(ids)))
        db_session.commit()


@pytest.fixture
def test_client(db_session: Session, created_client_ids):
    repo = ClientRepository(db_session)
    c = repo.create(name="Cliente Nota Teste", cpf="11122233344")
    db_session.commit()
    created_client_ids.append(c.id)
    return c


@pytest.fixture
def second_user(db_session: Session, grant_permissions):
    password = "Valid@1234"
    user = UserRepository(db_session).create(
        name="Second User",
        email="e2e_second_note@test.com",
        hashed_password=_hash(password),
        role=Role.USER,
    )
    grant_permissions(user.id, ["clientes"])
    yield {"id": user.id, "email": user.email, "password": password}
    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()


@pytest.fixture
def second_user_headers(client, second_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": second_user["email"], "password": second_user["password"]},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def notes_url(client_id: int) -> str:
    return f"{CLIENTS_URL}/{client_id}/notes"


def note_url(client_id: int, note_id: int) -> str:
    return f"{CLIENTS_URL}/{client_id}/notes/{note_id}"


class TestCreateNote:
    def test_returns_401_without_token(self, client, test_client):
        response = client.post(notes_url(test_client.id), json={"content": "Nota"})

        assert response.status_code == 401

    def test_creates_note_returns_201(
        self, client, user_headers, active_user, test_client
    ):
        response = client.post(
            notes_url(test_client.id),
            json={"content": "Observação do cliente"},
            headers=user_headers,
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["content"] == "Observação do cliente"
        assert data["client_id"] == test_client.id
        assert data["created_by"] == active_user["id"]
        assert data["updated_by"] is None
        assert data["created_by_name"] is not None
        assert data["updated_by_name"] is None

    def test_returns_404_when_client_not_found(self, client, user_headers):
        response = client.post(
            notes_url(99999),
            json={"content": "Nota"},
            headers=user_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CLIENT_NOT_FOUND"

    def test_returns_422_when_content_empty(self, client, user_headers, test_client):
        response = client.post(
            notes_url(test_client.id),
            json={"content": ""},
            headers=user_headers,
        )

        assert response.status_code == 422

    def test_returns_422_when_content_missing(self, client, user_headers, test_client):
        response = client.post(
            notes_url(test_client.id),
            json={},
            headers=user_headers,
        )

        assert response.status_code == 422


class TestListNotes:
    def test_returns_401_without_token(self, client, test_client):
        response = client.get(notes_url(test_client.id))

        assert response.status_code == 401

    def test_returns_404_when_client_not_found(self, client, user_headers):
        response = client.get(notes_url(99999), headers=user_headers)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CLIENT_NOT_FOUND"

    def test_returns_paginated_structure(self, client, user_headers, test_client):
        response = client.get(notes_url(test_client.id), headers=user_headers)
        body = response.json()

        assert response.status_code == 200
        assert body["success"] is True
        assert "data" in body
        assert "meta" in body

    def test_notes_ordered_newest_first(self, client, user_headers, test_client):
        client.post(
            notes_url(test_client.id),
            json={"content": "Primeira"},
            headers=user_headers,
        )
        client.post(
            notes_url(test_client.id), json={"content": "Segunda"}, headers=user_headers
        )

        response = client.get(notes_url(test_client.id), headers=user_headers)
        notes = response.json()["data"]

        assert len(notes) >= 2
        assert notes[0]["content"] == "Segunda"
        assert notes[1]["content"] == "Primeira"

    def test_pagination_respects_limit(self, client, user_headers, test_client):
        for i in range(3):
            client.post(
                notes_url(test_client.id),
                json={"content": f"Nota {i}"},
                headers=user_headers,
            )

        response = client.get(
            f"{notes_url(test_client.id)}?limit=2", headers=user_headers
        )

        assert len(response.json()["data"]) <= 2


class TestUpdateNote:
    def test_returns_401_without_token(self, client, test_client):
        response = client.patch(note_url(test_client.id, 1), json={"content": "X"})

        assert response.status_code == 401

    def test_author_can_edit_note(self, client, user_headers, active_user, test_client):
        create_resp = client.post(
            notes_url(test_client.id),
            json={"content": "Original"},
            headers=user_headers,
        )
        note_id = create_resp.json()["data"]["id"]

        response = client.patch(
            note_url(test_client.id, note_id),
            json={"content": "Editado"},
            headers=user_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["content"] == "Editado"
        assert data["updated_by"] == active_user["id"]
        assert data["updated_by_name"] is not None

    def test_other_user_receives_403(
        self, client, user_headers, second_user_headers, test_client
    ):
        create_resp = client.post(
            notes_url(test_client.id),
            json={"content": "Nota do primeiro usuário"},
            headers=user_headers,
        )
        note_id = create_resp.json()["data"]["id"]

        response = client.patch(
            note_url(test_client.id, note_id),
            json={"content": "Tentativa de edição"},
            headers=second_user_headers,
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_admin_can_edit_any_note(
        self, client, user_headers, admin_headers, admin_user, test_client
    ):
        create_resp = client.post(
            notes_url(test_client.id),
            json={"content": "Nota de usuário comum"},
            headers=user_headers,
        )
        note_id = create_resp.json()["data"]["id"]

        response = client.patch(
            note_url(test_client.id, note_id),
            json={"content": "Editado pelo admin"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["content"] == "Editado pelo admin"
        assert data["updated_by"] == admin_user["id"]

    def test_returns_404_when_client_not_found(self, client, user_headers):
        response = client.patch(
            note_url(99999, 1),
            json={"content": "X"},
            headers=user_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CLIENT_NOT_FOUND"

    def test_returns_404_when_note_not_found(self, client, user_headers, test_client):
        response = client.patch(
            note_url(test_client.id, 99999),
            json={"content": "X"},
            headers=user_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CLIENT_NOTE_NOT_FOUND"

    def test_returns_404_when_note_belongs_to_different_client(
        self, client, user_headers, test_client, db_session, created_client_ids
    ):
        other_client = ClientRepository(db_session).create(
            name="Outro Cliente", cpf="99988877766"
        )
        db_session.commit()
        created_client_ids.append(other_client.id)

        create_resp = client.post(
            notes_url(other_client.id),
            json={"content": "Nota do outro cliente"},
            headers=user_headers,
        )
        note_id = create_resp.json()["data"]["id"]

        response = client.patch(
            note_url(test_client.id, note_id),
            json={"content": "Tentativa cruzada"},
            headers=user_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CLIENT_NOTE_NOT_FOUND"

    def test_returns_422_when_content_empty(self, client, user_headers, test_client):
        create_resp = client.post(
            notes_url(test_client.id),
            json={"content": "Nota"},
            headers=user_headers,
        )
        note_id = create_resp.json()["data"]["id"]

        response = client.patch(
            note_url(test_client.id, note_id),
            json={"content": ""},
            headers=user_headers,
        )

        assert response.status_code == 422
