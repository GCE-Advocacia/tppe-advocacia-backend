import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.clients.model import Client
from app.modules.clients.repository import ClientRepository
from app.modules.payments.model import Payment

PAYMENTS_URL = "/api/v1/payments"
USERS_URL = "/api/v1/users"


@pytest.fixture
def payment_client(db_session: Session, admin_user):
    # Depende de admin_user para ser finalizada ANTES da remoção do usuário
    # (FK payments.created_by -> users.id).
    c = ClientRepository(db_session).create(
        name="Cliente Vencimentos", cpf="98765432100"
    )
    db_session.commit()
    yield c
    db_session.rollback()
    db_session.execute(delete(Payment).where(Payment.client_id == c.id))
    db_session.execute(delete(Client).where(Client.id == c.id))
    db_session.commit()


@pytest.fixture
def payment(client, admin_headers, payment_client):
    response = client.post(
        PAYMENTS_URL, json=payment_payload(payment_client.id), headers=admin_headers
    )
    assert response.status_code == 201
    return response.json()


def payment_payload(client_id: int, **kwargs) -> dict:
    payload = {
        "client_id": client_id,
        "payment_date": "2099-01-10",
        "amount": "1500.00",
        "description": "Parcela de honorários",
    }
    payload.update(kwargs)
    return payload


def set_can_view_payments(client, admin_headers, user_id: int, value: bool):
    response = client.patch(
        f"{USERS_URL}/{user_id}",
        json={"can_view_payments": value},
        headers=admin_headers,
    )
    assert response.status_code == 200
    return response


def assert_forbidden(response) -> None:
    assert response.status_code == 403
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "FORBIDDEN"


class TestUserWithoutPermission:
    def test_list_returns_403(self, client, user_headers):
        assert_forbidden(client.get(PAYMENTS_URL, headers=user_headers))

    def test_get_by_id_returns_403(self, client, user_headers, payment):
        assert_forbidden(
            client.get(f"{PAYMENTS_URL}/{payment['id']}", headers=user_headers)
        )

    def test_user_read_exposes_flag_false_by_default(
        self, client, admin_headers, active_user
    ):
        response = client.get(f"{USERS_URL}/{active_user['id']}", headers=admin_headers)

        assert response.json()["data"]["can_view_payments"] is False


class TestGrantPermission:
    def test_patch_returns_flag(self, client, admin_headers, active_user):
        response = set_can_view_payments(client, admin_headers, active_user["id"], True)

        assert response.json()["data"]["can_view_payments"] is True

    def test_same_token_can_list_after_grant(
        self, client, admin_headers, user_headers, active_user, payment
    ):
        set_can_view_payments(client, admin_headers, active_user["id"], True)

        response = client.get(PAYMENTS_URL, headers=user_headers)

        assert response.status_code == 200
        assert payment["id"] in [p["id"] for p in response.json()]

    def test_same_token_can_get_by_id_after_grant(
        self, client, admin_headers, user_headers, active_user, payment
    ):
        set_can_view_payments(client, admin_headers, active_user["id"], True)

        response = client.get(f"{PAYMENTS_URL}/{payment['id']}", headers=user_headers)

        assert response.status_code == 200
        assert response.json()["id"] == payment["id"]

    def test_user_with_permission_cannot_create(
        self, client, admin_headers, user_headers, active_user, payment_client
    ):
        set_can_view_payments(client, admin_headers, active_user["id"], True)

        assert_forbidden(
            client.post(
                PAYMENTS_URL,
                json=payment_payload(payment_client.id),
                headers=user_headers,
            )
        )

    def test_user_with_permission_cannot_update(
        self, client, admin_headers, user_headers, active_user, payment
    ):
        set_can_view_payments(client, admin_headers, active_user["id"], True)

        assert_forbidden(
            client.patch(
                f"{PAYMENTS_URL}/{payment['id']}",
                json={"description": "Alterado"},
                headers=user_headers,
            )
        )

    def test_user_with_permission_cannot_delete(
        self, client, admin_headers, user_headers, active_user, payment
    ):
        set_can_view_payments(client, admin_headers, active_user["id"], True)

        assert_forbidden(
            client.delete(f"{PAYMENTS_URL}/{payment['id']}", headers=user_headers)
        )

    def test_grant_is_audited_as_user_updated(self, client, admin_headers, active_user):
        set_can_view_payments(client, admin_headers, active_user["id"], True)

        response = client.get(
            "/api/v1/audit-logs",
            params={"action": "USER_UPDATED", "limit": 100},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert any(
            log["target_user_id"] == active_user["id"]
            for log in response.json()["data"]
        )


class TestRevokePermission:
    def test_revoke_blocks_same_token_without_relogin(
        self, client, admin_headers, user_headers, active_user, payment
    ):
        set_can_view_payments(client, admin_headers, active_user["id"], True)
        assert client.get(PAYMENTS_URL, headers=user_headers).status_code == 200

        set_can_view_payments(client, admin_headers, active_user["id"], False)

        assert_forbidden(client.get(PAYMENTS_URL, headers=user_headers))
        assert_forbidden(
            client.get(f"{PAYMENTS_URL}/{payment['id']}", headers=user_headers)
        )


class TestAdminAccess:
    def test_admin_crud(self, client, admin_headers, payment_client):
        created = client.post(
            PAYMENTS_URL,
            json=payment_payload(payment_client.id),
            headers=admin_headers,
        )
        assert created.status_code == 201
        payment_id = created.json()["id"]

        listed = client.get(PAYMENTS_URL, headers=admin_headers)
        assert listed.status_code == 200
        assert payment_id in [p["id"] for p in listed.json()]

        fetched = client.get(f"{PAYMENTS_URL}/{payment_id}", headers=admin_headers)
        assert fetched.status_code == 200

        updated = client.patch(
            f"{PAYMENTS_URL}/{payment_id}",
            json={"description": "Atualizado"},
            headers=admin_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "Atualizado"

        deleted = client.delete(f"{PAYMENTS_URL}/{payment_id}", headers=admin_headers)
        assert deleted.status_code == 204

        missing = client.get(f"{PAYMENTS_URL}/{payment_id}", headers=admin_headers)
        assert missing.status_code == 404
