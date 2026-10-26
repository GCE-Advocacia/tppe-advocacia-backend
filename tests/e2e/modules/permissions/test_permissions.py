import pytest
from fastapi.routing import APIRoute
from sqlalchemy import delete

from app.main import app
from app.modules.audit_logs.model import AuditLog
from app.modules.clients.model import Client
from app.modules.clients.repository import ClientRepository
from app.modules.payments.model import Payment
from app.modules.users.model import User
from app.shared.deps.auth import require_admin
from app.shared.types import PermissionKey


@pytest.fixture
def created_permission_users(db_session):
    ids = []
    yield ids
    db_session.rollback()
    db_session.execute(delete(AuditLog).where(AuditLog.target_user_id.in_(ids)))
    db_session.execute(delete(User).where(User.id.in_(ids)))
    db_session.commit()


@pytest.fixture
def payment_client_id(db_session):
    client = ClientRepository(db_session).create(
        name="Cliente Pagamentos Permissoes", cpf="78978978901"
    )
    db_session.commit()
    client_id = client.id
    yield client_id
    db_session.rollback()
    db_session.execute(delete(Payment).where(Payment.client_id == client_id))
    db_session.execute(delete(Client).where(Client.id == client_id))
    db_session.commit()


@pytest.fixture
def user_permissions():
    # Cada teste começa com um funcionário sem nenhuma aba marcada (D4).
    return []


REPRESENTATIVE_ROUTES = [
    ("landing_page", "PATCH", "/api/v1/office-config", {}),
    ("artigos", "GET", "/api/v1/articles/admin", None),
    ("leads", "GET", "/api/v1/leads", None),
    ("clientes", "GET", "/api/v1/clients", None),
    ("agenda", "GET", "/api/v1/appointments", None),
    ("pagamentos", "GET", "/api/v1/payments", None),
    ("processos", "GET", "/api/v1/processes", None),
    ("tarefas", "GET", "/api/v1/tasks/kanban", None),
    ("notificacoes", "GET", "/api/v1/notifications/preferences", None),
    ("logs_api", "GET", "/api/v1/external-api-logs", None),
    ("feriados", "GET", "/api/v1/forensic-holidays", None),
    ("financeiro", "GET", "/api/v1/finance/summary", None),
]


def assert_forbidden(response):
    assert response.status_code == 403
    assert response.json() == {
        "success": False,
        "error": {"code": "FORBIDDEN", "message": "Insufficient permissions"},
    }


@pytest.mark.parametrize(
    ("key", "method", "path", "body"),
    REPRESENTATIVE_ROUTES,
    ids=[row[0] for row in REPRESENTATIVE_ROUTES],
)
def test_each_tab_grants_full_access_and_revocation_blocks_same_token(
    client,
    user_headers,
    admin_headers,
    active_user,
    grant_permissions,
    key,
    method,
    path,
    body,
):
    def call(headers):
        return client.request(method, path, headers=headers, json=body)

    assert_forbidden(call(user_headers))
    grant_permissions(active_user["id"], [key])
    assert call(user_headers).status_code in (200, 201, 204)
    assert call(admin_headers).status_code in (200, 201, 204)
    grant_permissions(active_user["id"], [])
    assert_forbidden(call(user_headers))


def test_payments_permission_allows_crud_and_reminders(
    client, user_headers, active_user, grant_permissions, payment_client_id
):
    grant_permissions(active_user["id"], ["pagamentos"])
    created = client.post(
        "/api/v1/payments",
        json={
            "client_id": payment_client_id,
            "payment_date": "2026-12-20",
            "amount": "100.00",
        },
        headers=user_headers,
    )
    assert created.status_code == 201
    payment_id = created.json()["id"]
    assert created.json()["created_by"] == active_user["id"]
    assert (
        client.get(f"/api/v1/payments/{payment_id}", headers=user_headers).status_code
        == 200
    )
    assert (
        client.get("/api/v1/payments/reminders", headers=user_headers).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/payments/{payment_id}/reminders", headers=user_headers
        ).status_code
        == 200
    )
    updated = client.patch(
        f"/api/v1/payments/{payment_id}",
        json={"description": "Parcela alterada"},
        headers=user_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Parcela alterada"
    assert (
        client.delete(
            f"/api/v1/payments/{payment_id}", headers=user_headers
        ).status_code
        == 204
    )


def test_catalog_is_admin_only_and_ordered(client, admin_headers, user_headers):
    assert_forbidden(client.get("/api/v1/permissions", headers=user_headers))
    response = client.get("/api/v1/permissions", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    catalog = response.json()["data"]
    assert [row["key"] for row in catalog] == [key.value for key in PermissionKey]
    assert [row["sort_order"] for row in catalog] == list(range(1, 13))
    assert [row["name"] for row in catalog] == [
        "Landing Page",
        "Artigos",
        "Leads",
        "Clientes",
        "Agenda",
        "Pagamentos",
        "Processos",
        "Tarefas",
        "Notificações",
        "Logs DataJud",
        "Feriados",
        "Financeiro",
    ]


def test_processes_shared_selectors_do_not_grant_other_tabs(
    client, user_headers, active_user, grant_permissions
):
    grant_permissions(active_user["id"], ["processos"])
    for path in ("/api/v1/clients", "/api/v1/users", "/api/v1/processes"):
        assert client.get(path, headers=user_headers).status_code == 200

    response = client.post(
        "/api/v1/tasks", json={"title": "Tarefa do processo"}, headers=user_headers
    )
    assert response.status_code == 201
    task_id = response.json()["data"]["id"]
    try:
        assert (
            client.patch(
                f"/api/v1/tasks/{task_id}",
                json={"title": "Atualizada"},
                headers=user_headers,
            ).status_code
            == 200
        )
        assert_forbidden(client.get("/api/v1/tasks/kanban", headers=user_headers))
        assert_forbidden(
            client.patch(
                "/api/v1/clients/999", json={"name": "Bloqueado"}, headers=user_headers
            )
        )
        # Os prazos da tela de Processos não ficam sob /processes/*.
        assert (
            client.patch(
                "/api/v1/deadlines/999",
                json={"deadline_type": "Teste"},
                headers=user_headers,
            ).status_code
            == 404
        )
    finally:
        assert (
            client.delete(f"/api/v1/tasks/{task_id}", headers=user_headers).status_code
            == 204
        )


def test_user_selector_only_lists_active_users_for_employees(
    client, user_headers, active_user, inactive_user, admin_user, grant_permissions
):
    grant_permissions(active_user["id"], ["tarefas"])
    for query in ("?is_active=false&limit=100", "?role=ADMIN&limit=100"):
        response = client.get(f"/api/v1/users{query}", headers=user_headers)
        assert response.status_code == 200
        items = response.json()["data"]
        assert all(item["is_active"] for item in items)
        emails = {item["email"] for item in items}
        assert inactive_user["email"] not in emails
        assert active_user["email"] in emails


def test_sensitive_admin_only_routes(
    client, user_headers, active_user, grant_permissions
):
    grant_permissions(active_user["id"], [key.value for key in PermissionKey])
    for method, path, body in (
        ("GET", "/api/v1/permissions", None),
        ("PATCH", f"/api/v1/users/{active_user['id']}", {"role": "ADMIN"}),
        ("GET", "/api/v1/audit-logs", None),
        ("DELETE", "/api/v1/clients/999?confirm=true", None),
    ):
        assert_forbidden(client.request(method, path, headers=user_headers, json=body))


def test_admin_sets_permissions_on_create_and_replaces_them_on_update(
    client, admin_headers, created_permission_users
):
    created = client.post(
        "/api/v1/users",
        json={
            "name": "Funcionario Permissoes",
            "email": "permissoes-create@example.com",
            "permissions": ["clientes", "pagamentos"],
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    user_id = created.json()["data"]["id"]
    created_permission_users.append(user_id)
    assert created.json()["data"]["role"] == "USER"
    assert created.json()["data"]["permissions"] == ["clientes", "pagamentos"]

    updated = client.patch(
        f"/api/v1/users/{user_id}",
        json={"permissions": ["processos"]},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["permissions"] == ["processos"]
    assert client.get(f"/api/v1/users/{user_id}", headers=admin_headers).json()["data"][
        "permissions"
    ] == ["processos"]
    logs = client.get(
        "/api/v1/audit-logs?action=USER_UPDATED", headers=admin_headers
    ).json()["data"]
    assert any(log["target_user_id"] == user_id for log in logs)

    cleared = client.patch(
        f"/api/v1/users/{user_id}", json={"permissions": []}, headers=admin_headers
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["permissions"] == []


def test_new_user_has_no_permissions_by_default(
    client, admin_headers, created_permission_users
):
    created = client.post(
        "/api/v1/users",
        json={"name": "Sem Permissoes", "email": "sem-permissoes@example.com"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    created_permission_users.append(created.json()["data"]["id"])
    assert created.json()["data"]["permissions"] == []


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_unknown_permission_key_is_validation_error(
    client, admin_headers, active_user, method
):
    if method == "POST":
        path = "/api/v1/users"
        body = {
            "name": "Invalido",
            "email": "invalid-key@example.com",
            "permissions": ["inexistente"],
        }
    else:
        path = f"/api/v1/users/{active_user['id']}"
        body = {"permissions": ["inexistente"]}
    response = client.request(method, path, json=body, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


PUBLIC_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    ("POST", "/api/v1/leads"),
    ("GET", "/api/v1/office-config"),
    ("GET", "/api/v1/office-config/themes"),
    ("GET", "/api/v1/office-config/themes/quota"),
    ("GET", "/api/v1/articles"),
    ("GET", "/api/v1/articles/{article_id}"),
    ("GET", "/api/v1/media/logos/{filename}"),
    ("GET", "/api/v1/media/{filename}"),
    ("GET", "/api/v1/integrations/google/callback"),
}


def _has_access_guard(dependant):
    return any(
        dep.call is require_admin
        or getattr(dep.call, "required_permissions", None)
        or _has_access_guard(dep)
        for dep in dependant.dependencies
    )


def test_non_public_api_routes_are_not_only_authenticated():
    unguarded = [
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")
        for method in route.methods
        if (method, route.path) not in PUBLIC_ROUTES
        and not _has_access_guard(route.dependant)
    ]
    assert not unguarded, f"Rotas sem permissão por aba ou require_admin: {unguarded}"
