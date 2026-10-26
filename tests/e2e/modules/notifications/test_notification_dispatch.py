import uuid

import bcrypt
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.clients.model import Client
from app.modules.leads.model import Lead
from app.modules.processes.model import Process
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.types import Role


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@pytest.fixture
def other_user(db_session: Session, grant_permissions):
    password = "Valid@1234"
    user = UserRepository(db_session).create(
        name="Other Lawyer",
        email="e2e_other_lawyer@test.com",
        hashed_password=_hash(password),
        role=Role.USER,
    )
    grant_permissions(user.id, ["processos"])
    yield {"id": user.id, "email": user.email, "password": password}
    db_session.rollback()
    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()


@pytest.fixture
def other_user_headers(client, other_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": other_user["email"], "password": other_user["password"]},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def created_process_ids(db_session: Session):
    ids: list[int] = []
    yield ids
    db_session.execute(delete(Process).where(Process.id.in_(ids)))
    db_session.commit()


@pytest.fixture
def created_client_ids(db_session: Session):
    ids: list[int] = []
    yield ids
    db_session.execute(delete(Client).where(Client.id.in_(ids)))
    db_session.commit()


@pytest.fixture
def process_owned_by_other(
    client,
    other_user_headers,
    fake_email,
    created_process_ids,
):
    """Process created by other_user — fake_email is cleared after creation."""
    response = client.post(
        "/api/v1/processes",
        json={
            "number": "9999999-99.2024.8.26.0100",
            "court": "TJSP",
            "action_type": "Ação Cível",
        },
        headers=other_user_headers,
    )
    assert response.status_code == 201
    process_id = response.json()["data"]["id"]
    created_process_ids.append(process_id)
    fake_email.sent.clear()
    return process_id


class TestMovementNotifications:
    def test_other_user_movement_notifies_creator(
        self, client, user_headers, fake_email, process_owned_by_other, other_user
    ):
        response = client.post(
            f"/api/v1/processes/{process_owned_by_other}/movements",
            json={"title": "Audiência marcada"},
            headers=user_headers,
        )
        assert response.status_code == 201

        recipients = [e["to"] for e in fake_email.sent]
        assert other_user["email"] in recipients
        subjects = [e["subject"] for e in fake_email.sent]
        assert any("9999999-99.2024.8.26.0100" in s for s in subjects)

    def test_creator_self_movement_does_not_notify_self(
        self,
        client,
        other_user_headers,
        fake_email,
        process_owned_by_other,
        other_user,
    ):
        response = client.post(
            f"/api/v1/processes/{process_owned_by_other}/movements",
            json={"title": "Eu mesmo movimentei"},
            headers=other_user_headers,
        )
        assert response.status_code == 201

        recipients = [e["to"] for e in fake_email.sent]
        assert other_user["email"] not in recipients


class TestStatusChangeNotifications:
    def test_other_user_status_change_notifies_creator(
        self, client, user_headers, fake_email, process_owned_by_other, other_user
    ):
        response = client.patch(
            f"/api/v1/processes/{process_owned_by_other}/status",
            json={"status": "SUSPENSO", "reason": "aguardando"},
            headers=user_headers,
        )
        assert response.status_code == 200

        recipients = [e["to"] for e in fake_email.sent]
        assert other_user["email"] in recipients
        assert any("alterado" in e["subject"].lower() for e in fake_email.sent)


class TestLeadAssignmentNotifications:
    def test_assigning_lead_notifies_new_assignee(
        self,
        client,
        admin_headers,
        fake_email,
        active_user,
        db_session: Session,
    ):
        unique_email = f"lead_notif_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = client.post(
            "/api/v1/leads",
            json={
                "name": "Lead Notif",
                "email": unique_email,
                "phone": "11999999999",
            },
        )
        assert create_resp.status_code == 201
        lead_id = create_resp.json()["data"]["id"]
        fake_email.sent.clear()

        try:
            response = client.patch(
                f"/api/v1/leads/{lead_id}",
                json={"assigned_to": active_user["id"]},
                headers=admin_headers,
            )
            assert response.status_code == 200

            recipients = [e["to"] for e in fake_email.sent]
            assert active_user["email"] in recipients
            assert any("lead" in e["subject"].lower() for e in fake_email.sent)
        finally:
            db_session.execute(delete(Lead).where(Lead.id == lead_id))
            db_session.commit()

    def test_admin_self_assigning_does_not_notify_self(
        self,
        client,
        admin_headers,
        fake_email,
        admin_user,
        db_session: Session,
    ):
        unique_email = f"lead_self_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = client.post(
            "/api/v1/leads",
            json={"name": "Lead Self", "email": unique_email},
        )
        assert create_resp.status_code == 201
        lead_id = create_resp.json()["data"]["id"]
        fake_email.sent.clear()

        try:
            response = client.patch(
                f"/api/v1/leads/{lead_id}",
                json={"assigned_to": admin_user["id"]},
                headers=admin_headers,
            )
            assert response.status_code == 200

            recipients = [e["to"] for e in fake_email.sent]
            assert admin_user["email"] not in recipients
        finally:
            db_session.execute(delete(Lead).where(Lead.id == lead_id))
            db_session.commit()
