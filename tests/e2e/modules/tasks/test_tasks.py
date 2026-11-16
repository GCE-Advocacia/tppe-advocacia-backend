import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.tasks.model import Task


@pytest.fixture
def fake_email(queued_email):
    # As notificações vão para a fila.
    return queued_email


TASKS_URL = "/api/v1/tasks"


@pytest.fixture(autouse=True)
def cleanup_tasks(db_session: Session):
    yield
    db_session.rollback()
    db_session.execute(delete(Task))
    db_session.commit()


class TestCreateTask:
    def test_returns_201(self, client, user_headers):
        response = client.post(
            TASKS_URL, json={"title": "Revisar contrato"}, headers=user_headers
        )
        assert response.status_code == 201

    def test_returns_401_without_token(self, client):
        response = client.post(TASKS_URL, json={"title": "X"})
        assert response.status_code == 401

    def test_defaults_status_to_todo(self, client, user_headers):
        response = client.post(TASKS_URL, json={"title": "X"}, headers=user_headers)
        data = response.json()["data"]
        assert data["status"] == "TODO"
        assert data["priority"] == "MEDIUM"
        assert data["order"] == 0

    def test_invalid_assignee_returns_422(self, client, user_headers):
        response = client.post(
            TASKS_URL,
            json={"title": "X", "assigned_to": 999999},
            headers=user_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "ASSIGNEE_NOT_FOUND"

    def test_invalid_client_returns_422(self, client, user_headers):
        response = client.post(
            TASKS_URL,
            json={"title": "X", "client_id": 999999},
            headers=user_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "TASK_CLIENT_NOT_FOUND"

    def test_invalid_process_returns_422(self, client, user_headers):
        response = client.post(
            TASKS_URL,
            json={"title": "X", "process_id": 999999},
            headers=user_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "TASK_PROCESS_NOT_FOUND"

    def test_missing_title_returns_422(self, client, user_headers):
        response = client.post(TASKS_URL, json={}, headers=user_headers)
        assert response.status_code == 422

    def test_dispatches_notification_when_assigned(
        self, client, user_headers, admin_user, fake_email
    ):
        client.post(
            TASKS_URL,
            json={"title": "Atribuída", "assigned_to": admin_user["id"]},
            headers=user_headers,
        )
        assert any("Atribuída" in m["subject"] for m in fake_email.sent)

    def test_self_assignment_does_not_notify(
        self, client, user_headers, active_user, fake_email
    ):
        fake_email.sent.clear()
        client.post(
            TASKS_URL,
            json={"title": "Pra mim", "assigned_to": active_user["id"]},
            headers=user_headers,
        )
        assert fake_email.sent == []


class TestListTasks:
    def test_returns_401_without_token(self, client):
        assert client.get(TASKS_URL).status_code == 401

    def test_returns_paginated_structure(self, client, user_headers):
        body = client.get(TASKS_URL, headers=user_headers).json()
        assert "data" in body
        assert "meta" in body

    def test_filters_by_status(self, client, user_headers):
        client.post(TASKS_URL, json={"title": "A"}, headers=user_headers)
        b = client.post(TASKS_URL, json={"title": "B"}, headers=user_headers).json()[
            "data"
        ]
        client.patch(
            f"{TASKS_URL}/{b['id']}/move",
            json={"status": "DONE", "order": 0},
            headers=user_headers,
        )

        items = client.get(f"{TASKS_URL}?status=DONE", headers=user_headers).json()[
            "data"
        ]

        assert all(t["status"] == "DONE" for t in items)
        assert any(t["title"] == "B" for t in items)


class TestGetTask:
    def test_returns_200(self, client, user_headers):
        created = client.post(
            TASKS_URL, json={"title": "X"}, headers=user_headers
        ).json()["data"]
        response = client.get(f"{TASKS_URL}/{created['id']}", headers=user_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == created["id"]

    def test_returns_404(self, client, user_headers):
        response = client.get(f"{TASKS_URL}/999999", headers=user_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


class TestUpdateTask:
    def test_partial_update(self, client, user_headers):
        created = client.post(
            TASKS_URL, json={"title": "X"}, headers=user_headers
        ).json()["data"]
        response = client.patch(
            f"{TASKS_URL}/{created['id']}",
            json={"title": "Renomeado"},
            headers=user_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["title"] == "Renomeado"

    def test_changing_assignee_dispatches_notification(
        self, client, user_headers, admin_user, fake_email
    ):
        created = client.post(
            TASKS_URL, json={"title": "X"}, headers=user_headers
        ).json()["data"]
        fake_email.sent.clear()

        client.patch(
            f"{TASKS_URL}/{created['id']}",
            json={"assigned_to": admin_user["id"]},
            headers=user_headers,
        )

        assert len(fake_email.sent) >= 1

    def test_status_change_via_patch_renumbers(self, client, user_headers):
        a = client.post(TASKS_URL, json={"title": "a"}, headers=user_headers).json()[
            "data"
        ]
        b = client.post(TASKS_URL, json={"title": "b"}, headers=user_headers).json()[
            "data"
        ]

        client.patch(
            f"{TASKS_URL}/{a['id']}",
            json={"status": "DONE"},
            headers=user_headers,
        )

        refreshed_b = client.get(f"{TASKS_URL}/{b['id']}", headers=user_headers).json()[
            "data"
        ]
        assert refreshed_b["order"] == 0


class TestDeleteTask:
    def test_creator_can_delete(self, client, user_headers):
        created = client.post(
            TASKS_URL, json={"title": "X"}, headers=user_headers
        ).json()["data"]
        response = client.delete(f"{TASKS_URL}/{created['id']}", headers=user_headers)
        assert response.status_code == 204

    def test_admin_can_delete_others_task(self, client, user_headers, admin_headers):
        created = client.post(
            TASKS_URL, json={"title": "X"}, headers=user_headers
        ).json()["data"]
        response = client.delete(f"{TASKS_URL}/{created['id']}", headers=admin_headers)
        assert response.status_code == 204

    def test_other_user_forbidden(self, client, admin_headers, user_headers):
        created = client.post(
            TASKS_URL, json={"title": "X"}, headers=admin_headers
        ).json()["data"]
        response = client.delete(f"{TASKS_URL}/{created['id']}", headers=user_headers)
        assert response.status_code == 403
