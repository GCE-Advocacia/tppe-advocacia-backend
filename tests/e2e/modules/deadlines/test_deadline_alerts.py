import bcrypt
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.deadlines.model import Deadline, DeadlineAlert
from app.modules.deadlines.service import EXPIRED_DAYS_BEFORE
from app.modules.processes.model import Process
from app.modules.processes.repository import ProcessRepository
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.shared.types import Role


@pytest.fixture
def cleanup_processes(db_session: Session):
    ids: list[int] = []
    yield ids
    deadline_ids = list(
        db_session.scalars(select(Deadline.id).where(Deadline.process_id.in_(ids)))
    )
    if deadline_ids:
        db_session.execute(
            delete(DeadlineAlert).where(DeadlineAlert.deadline_id.in_(deadline_ids))
        )
    db_session.execute(delete(Deadline).where(Deadline.process_id.in_(ids)))
    db_session.execute(delete(Process).where(Process.id.in_(ids)))
    db_session.commit()


@pytest.fixture
def process_fixture(db_session: Session, active_user, cleanup_processes) -> Process:
    p = ProcessRepository(db_session).create(
        number="99999999999999999991",
        court="TJDFT",
        action_type="Ação Cível",
        created_by=active_user["id"],
    )
    db_session.commit()
    cleanup_processes.append(p.id)
    return p


@pytest.fixture
def deadline_with_alerts(db_session: Session, client, user_headers, process_fixture):
    r = client.post(
        f"/api/v1/processes/{process_fixture.id}/deadlines",
        json={
            "start_date": "2026-05-11",
            "business_days": 5,
            "deadline_type": "Contestação",
        },
        headers=user_headers,
    )
    deadline_id = r.json()["data"]["id"]
    db_session.add(DeadlineAlert(deadline_id=deadline_id, days_before=15))
    db_session.add(
        DeadlineAlert(deadline_id=deadline_id, days_before=EXPIRED_DAYS_BEFORE)
    )
    db_session.commit()
    return {"process_id": process_fixture.id, "deadline_id": deadline_id}


@pytest.fixture
def other_user_headers(db_session: Session, client, grant_permissions):
    password = "Valid@1234"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = UserRepository(db_session).create(
        name="Other Alerts User",
        email="e2e_other_alerts@test.com",
        hashed_password=hashed,
        role=Role.USER,
    )
    grant_permissions(user.id, ["processos"])
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    token = response.json()["data"]["access_token"]
    yield {"Authorization": f"Bearer {token}"}
    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()


def _url(process_id: int, deadline_id: int) -> str:
    return f"/api/v1/processes/{process_id}/deadlines/{deadline_id}/alerts"


class TestListAlerts:
    def test_requires_auth(self, client, deadline_with_alerts):
        r = client.get(
            _url(
                deadline_with_alerts["process_id"],
                deadline_with_alerts["deadline_id"],
            )
        )
        assert r.status_code in (401, 403)

    def test_author_sees_history(self, client, user_headers, deadline_with_alerts):
        r = client.get(
            _url(
                deadline_with_alerts["process_id"],
                deadline_with_alerts["deadline_id"],
            ),
            headers=user_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2
        kinds = {item["kind"] for item in data}
        assert kinds == {"APPROACHING", "EXPIRED"}

    def test_admin_sees_history(self, client, admin_headers, deadline_with_alerts):
        r = client.get(
            _url(
                deadline_with_alerts["process_id"],
                deadline_with_alerts["deadline_id"],
            ),
            headers=admin_headers,
        )
        assert r.status_code == 200

    def test_non_author_non_admin_forbidden(
        self, client, other_user_headers, deadline_with_alerts
    ):
        r = client.get(
            _url(
                deadline_with_alerts["process_id"],
                deadline_with_alerts["deadline_id"],
            ),
            headers=other_user_headers,
        )
        assert r.status_code == 403

    def test_unknown_deadline_returns_404(self, client, user_headers, process_fixture):
        r = client.get(
            _url(process_fixture.id, 999999),
            headers=user_headers,
        )
        assert r.status_code == 404

    def test_deadline_of_another_process_returns_404(
        self, client, user_headers, db_session, deadline_with_alerts, cleanup_processes
    ):
        other = ProcessRepository(db_session).create(
            number="99999999999999999992",
            court="TJSP",
            action_type="x",
        )
        db_session.commit()
        cleanup_processes.append(other.id)
        r = client.get(
            _url(other.id, deadline_with_alerts["deadline_id"]),
            headers=user_headers,
        )
        assert r.status_code == 404
