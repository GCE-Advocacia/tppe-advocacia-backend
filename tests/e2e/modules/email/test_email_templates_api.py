from app.modules.email.registry import TEMPLATES

BASE = "/api/v1/email/templates"


class TestListTemplates:
    def test_admin_lists_every_template(self, client, admin_headers):
        response = client.get(BASE, headers=admin_headers)

        assert response.status_code == 200
        ids = [t["id"] for t in response.json()["data"]]
        assert sorted(ids) == sorted(TEMPLATES)
        assert all(t["name"] for t in response.json()["data"])

    def test_user_is_forbidden(self, client, user_headers):
        assert client.get(BASE, headers=user_headers).status_code == 403

    def test_requires_auth(self, client):
        assert client.get(BASE).status_code == 401


class TestPreview:
    def test_html_preview(self, client, admin_headers):
        response = client.get(f"{BASE}/password_reset/preview", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["format"] == "html"
        assert data["subject"] == "Redefinição de senha"
        assert data["content"].lstrip().startswith("<!DOCTYPE html>")

    def test_text_preview(self, client, admin_headers):
        response = client.get(
            f"{BASE}/notification.task_assigned/preview",
            params={"format": "text"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["format"] == "text"
        assert "Revisar contrato social" in data["content"]
        assert "<" not in data["content"]

    def test_unknown_template_returns_404(self, client, admin_headers):
        response = client.get(f"{BASE}/nao_existe/preview", headers=admin_headers)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "EMAIL_TEMPLATE_NOT_FOUND"

    def test_invalid_format_returns_422(self, client, admin_headers):
        response = client.get(
            f"{BASE}/password_reset/preview",
            params={"format": "pdf"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_user_is_forbidden(self, client, user_headers):
        response = client.get(f"{BASE}/password_reset/preview", headers=user_headers)
        assert response.status_code == 403
