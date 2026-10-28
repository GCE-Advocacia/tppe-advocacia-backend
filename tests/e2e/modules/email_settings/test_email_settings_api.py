import pytest
from sqlalchemy import delete, select, update

from app.main import app
from app.modules.audit_logs.model import AuditAction, AuditLog
from app.modules.email_settings.connection_test import (
    ConnectionTestReport,
    StepResult,
)
from app.modules.email_settings.deps import get_connection_tester
from app.modules.email_settings.model import EmailProfile

BASE = "/api/v1/email-settings/profiles"
SECRET = "senha-super-secreta-123"


class FakeTester:
    def __init__(self) -> None:
        self.ok = True
        self.configs: list = []

    def test(self, config) -> ConnectionTestReport:
        self.configs.append(config)
        if self.ok:
            return ConnectionTestReport([StepResult("connect", True, 1)])
        return ConnectionTestReport(
            [
                StepResult("connect", True, 1),
                StepResult("auth", False, 2, "535 credenciais inválidas"),
            ]
        )


@pytest.fixture
def tester():
    fake = FakeTester()
    app.dependency_overrides[get_connection_tester] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_connection_tester, None)


@pytest.fixture(autouse=True)
def reset_profiles(db_session):
    yield
    db_session.rollback()
    db_session.execute(
        update(EmailProfile).values(
            provider="smtp",
            host=None,
            port=587,
            security="starttls",
            username=None,
            secret_encrypted=None,
            from_email=None,
            from_name=None,
            reply_to=None,
            is_active=False,
            last_tested_at=None,
            last_test_ok=None,
            version=1,
            updated_by=None,
        )
    )
    db_session.execute(
        delete(AuditLog).where(AuditLog.action == AuditAction.EMAIL_SETTINGS_UPDATED)
    )
    db_session.commit()


def _primary(client, headers) -> dict:
    profiles = client.get(BASE, headers=headers).json()["data"]
    return next(p for p in profiles if p["priority"] == 1)


def _form(version: int, **overrides) -> dict:
    form = {
        "provider": "smtp",
        "host": "smtp.exemplo.com",
        "port": 587,
        "security": "starttls",
        "username": "conta@exemplo.com",
        "secret": SECRET,
        "from_email": "conta@exemplo.com",
        "from_name": "Escritório",
        "reply_to": None,
        "is_active": True,
        "version": version,
    }
    form.update(overrides)
    return form


class TestPermissions:
    def test_user_is_forbidden(self, client, user_headers):
        assert client.get(BASE, headers=user_headers).status_code == 403
        assert (
            client.put(f"{BASE}/1", json=_form(1), headers=user_headers).status_code
            == 403
        )
        assert (
            client.post(
                f"{BASE}/1/test-connection", json={}, headers=user_headers
            ).status_code
            == 403
        )

    def test_requires_auth(self, client):
        assert client.get(BASE).status_code == 401


class TestListAndSave:
    def test_lists_primary_and_fallback(self, client, admin_headers):
        response = client.get(BASE, headers=admin_headers)

        assert response.status_code == 200
        assert [p["priority"] for p in response.json()["data"]] == [1, 2]

    def test_response_never_contains_secret(
        self, client, admin_headers, tester, db_session
    ):
        profile = _primary(client, admin_headers)

        saved = client.put(
            f"{BASE}/{profile['id']}",
            json=_form(profile["version"]),
            headers=admin_headers,
        )
        listed = client.get(BASE, headers=admin_headers)

        assert saved.status_code == 200, saved.text
        assert saved.json()["data"]["has_secret"] is True
        assert SECRET not in saved.text
        assert SECRET not in listed.text
        stored = db_session.scalar(
            select(EmailProfile.secret_encrypted).where(
                EmailProfile.id == profile["id"]
            )
        )
        assert stored and SECRET not in stored

    def test_empty_secret_keeps_current(self, client, admin_headers, tester):
        profile = _primary(client, admin_headers)
        first = client.put(
            f"{BASE}/{profile['id']}",
            json=_form(profile["version"]),
            headers=admin_headers,
        ).json()["data"]

        second = client.put(
            f"{BASE}/{profile['id']}",
            json=_form(first["version"], secret="", from_name="Outro nome"),
            headers=admin_headers,
        )

        assert second.status_code == 200, second.text
        assert second.json()["data"]["has_secret"] is True
        # O teste de conexão do segundo save usou a senha já salva.
        assert tester.configs[-1].password == SECRET

    def test_stale_version_is_rejected(self, client, admin_headers, tester):
        profile = _primary(client, admin_headers)
        client.put(
            f"{BASE}/{profile['id']}",
            json=_form(profile["version"]),
            headers=admin_headers,
        )

        response = client.put(
            f"{BASE}/{profile['id']}",
            json=_form(profile["version"], from_name="Por cima"),
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_PROFILE_VERSION_CONFLICT"

    def test_failed_connection_is_not_saved(self, client, admin_headers, tester):
        tester.ok = False
        profile = _primary(client, admin_headers)

        response = client.put(
            f"{BASE}/{profile['id']}",
            json=_form(profile["version"]),
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "EMAIL_PROFILE_TEST_FAILED"
        assert _primary(client, admin_headers)["version"] == profile["version"]

    def test_incomplete_active_profile_is_rejected(self, client, admin_headers, tester):
        profile = _primary(client, admin_headers)

        response = client.put(
            f"{BASE}/{profile['id']}",
            json=_form(profile["version"], host=""),
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "EMAIL_PROFILE_INCOMPLETE"

    def test_audit_has_diff_without_secret(
        self, client, admin_headers, tester, db_session
    ):
        profile = _primary(client, admin_headers)
        client.put(
            f"{BASE}/{profile['id']}",
            json=_form(profile["version"]),
            headers=admin_headers,
        )

        log = db_session.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.EMAIL_SETTINGS_UPDATED
            )
        ).one()

        assert log.details["changes"]["secret"] == "alterado"
        assert log.details["changes"]["host"]["para"] == "smtp.exemplo.com"
        assert SECRET not in str(log.details)


class TestConnection:
    def test_returns_steps(self, client, admin_headers, tester):
        tester.ok = False
        profile = _primary(client, admin_headers)
        form = _form(profile["version"])
        form.pop("version")

        response = client.post(
            f"{BASE}/{profile['id']}/test-connection", json=form, headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ok"] is False
        assert data["steps"][-1] == {
            "step": "auth",
            "ok": False,
            "duration_ms": 2,
            "error": "535 credenciais inválidas",
        }
