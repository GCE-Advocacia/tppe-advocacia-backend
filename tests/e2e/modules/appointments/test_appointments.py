import bcrypt
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.appointments.model import Appointment
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.types import Role

URL = "/api/v1/appointments"
FUTURE = "2026-12-01T14:00:00Z"
FUTURE_LATER = "2026-12-15T09:00:00Z"
PAST = "2020-01-01T10:00:00Z"


@pytest.fixture
def created_appointments(db_session: Session, active_user, admin_user):
    ids: list[int] = []
    yield ids
    db_session.execute(delete(Appointment).where(Appointment.id.in_(ids)))
    db_session.commit()


@pytest.fixture
def other_user_headers(db_session: Session, client, grant_permissions):
    password = "Valid@1234"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = UserRepository(db_session).create(
        name="Other Agenda User",
        email="e2e_other_agenda@test.com",
        hashed_password=hashed,
        role=Role.USER,
    )
    grant_permissions(user.id, ["agenda"])
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    token = response.json()["data"]["access_token"]
    yield {"Authorization": f"Bearer {token}"}
    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()


def _create(client, headers, created_appointments, **overrides) -> dict:
    body = {
        "title": "Reunião inicial",
        "type": "REUNIAO",
        "starts_at": FUTURE,
        "duration_minutes": 60,
    }
    body.update(overrides)
    response = client.post(URL, json=body, headers=headers)
    if response.status_code == 201:
        created_appointments.append(response.json()["data"]["id"])
    return response


class TestCreate:
    def test_requires_auth(self, client):
        assert client.post(URL, json={}).status_code in (401, 403)

    def test_creates_appointment(self, client, user_headers, created_appointments):
        r = _create(client, user_headers, created_appointments)
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["title"] == "Reunião inicial"
        assert data["type"] == "REUNIAO"
        assert data["is_synced_to_google"] is False
        assert data["google_event_id"] is None

    def test_rejects_past_starts_at(self, client, user_headers, created_appointments):
        r = _create(client, user_headers, created_appointments, starts_at=PAST)
        assert r.status_code == 422

    def test_rejects_unknown_client(self, client, user_headers, created_appointments):
        r = _create(client, user_headers, created_appointments, client_id=999999)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "APPOINTMENT_CLIENT_NOT_FOUND"

    def test_rejects_unknown_process(self, client, user_headers, created_appointments):
        r = _create(client, user_headers, created_appointments, process_id=999999)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "APPOINTMENT_PROCESS_NOT_FOUND"


class TestList:
    def test_lists_only_own_appointments(
        self, client, user_headers, admin_headers, created_appointments
    ):
        _create(client, user_headers, created_appointments, title="do user")
        _create(client, admin_headers, created_appointments, title="do admin")

        r = client.get(URL, headers=user_headers)
        assert r.status_code == 200
        titles = [a["title"] for a in r.json()["data"]]
        assert "do user" in titles
        assert "do admin" not in titles

    def test_filters_by_type(self, client, user_headers, created_appointments):
        _create(client, user_headers, created_appointments, type="AUDIENCIA")
        _create(client, user_headers, created_appointments, type="REUNIAO")

        r = client.get(URL, headers=user_headers, params={"type": "AUDIENCIA"})
        assert r.status_code == 200
        assert all(a["type"] == "AUDIENCIA" for a in r.json()["data"])
        assert len(r.json()["data"]) >= 1


class TestGet:
    def test_owner_gets(self, client, user_headers, created_appointments):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        r = client.get(f"{URL}/{appt_id}", headers=user_headers)
        assert r.status_code == 200

    def test_admin_gets_other(
        self, client, user_headers, admin_headers, created_appointments
    ):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        assert client.get(f"{URL}/{appt_id}", headers=admin_headers).status_code == 200

    def test_non_owner_forbidden(
        self, client, user_headers, other_user_headers, created_appointments
    ):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        r = client.get(f"{URL}/{appt_id}", headers=other_user_headers)
        assert r.status_code == 403

    def test_unknown_returns_404(self, client, user_headers):
        assert client.get(f"{URL}/999999", headers=user_headers).status_code == 404


class TestUpdate:
    def test_owner_updates(self, client, user_headers, created_appointments):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        r = client.patch(
            f"{URL}/{appt_id}",
            json={"title": "Reunião remarcada", "starts_at": FUTURE_LATER},
            headers=user_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["title"] == "Reunião remarcada"

    def test_update_allows_past_starts_at(
        self, client, user_headers, created_appointments
    ):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        r = client.patch(
            f"{URL}/{appt_id}", json={"starts_at": PAST}, headers=user_headers
        )
        assert r.status_code == 200

    def test_non_owner_forbidden(
        self, client, user_headers, other_user_headers, created_appointments
    ):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        r = client.patch(
            f"{URL}/{appt_id}", json={"title": "hack"}, headers=other_user_headers
        )
        assert r.status_code == 403


class TestDelete:
    def test_owner_deletes(self, client, user_headers, created_appointments):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        assert (
            client.delete(f"{URL}/{appt_id}", headers=user_headers).status_code == 204
        )
        assert client.get(f"{URL}/{appt_id}", headers=user_headers).status_code == 404

    def test_non_owner_forbidden(
        self, client, user_headers, other_user_headers, created_appointments
    ):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        r = client.delete(f"{URL}/{appt_id}", headers=other_user_headers)
        assert r.status_code == 403

    def test_admin_deletes_other(
        self, client, user_headers, admin_headers, created_appointments
    ):
        appt_id = _create(client, user_headers, created_appointments).json()["data"][
            "id"
        ]
        assert (
            client.delete(f"{URL}/{appt_id}", headers=admin_headers).status_code == 204
        )
