from urllib.parse import parse_qs, urlparse

import pytest

from app.modules.google_calendar.oauth import GoogleOAuthFlow

BASE = "/api/v1/integrations/google-drive"


@pytest.fixture
def exchange(monkeypatch):
    monkeypatch.setattr(
        GoogleOAuthFlow, "exchange_code", lambda self, code: ("refresh", "drive.file")
    )


def connect(api) -> None:
    auth_url = api.client.get(f"{BASE}/auth-url", headers=api.headers(1)).json()[
        "data"
    ]["auth_url"]
    state = parse_qs(urlparse(auth_url).query)["state"][0]
    response = api.client.get(
        f"{BASE}/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == (
        "http://front.test/sistema/processos?google_drive=connected"
    )


def test_status_visible_to_any_user(drive_api):
    response = drive_api.client.get(f"{BASE}/status", headers=drive_api.headers(2))
    assert response.status_code == 200
    assert response.json()["data"] == {"connected": False, "email": None}


def test_status_requires_login(drive_api):
    assert drive_api.client.get(f"{BASE}/status").status_code == 401


def test_auth_url_and_disconnect_forbidden_for_non_admin(drive_api):
    headers = drive_api.headers(2)
    assert drive_api.client.get(f"{BASE}/auth-url", headers=headers).status_code == 403
    assert drive_api.client.delete(BASE, headers=headers).status_code == 403


def test_auth_url_uses_drive_scope_and_redirect(drive_api):
    auth_url = drive_api.client.get(
        f"{BASE}/auth-url", headers=drive_api.headers(1)
    ).json()["data"]["auth_url"]
    query = parse_qs(urlparse(auth_url).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["redirect_uri"][0].endswith("/integrations/google-drive/callback")
    assert "include_granted_scopes" not in query


def test_callback_with_error_param_redirects_with_error(drive_api):
    response = drive_api.client.get(
        f"{BASE}/callback", params={"error": "access_denied"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"].endswith(
        "/sistema/processos?google_drive=error"
    )


def test_callback_with_forged_state_redirects_with_error(drive_api, exchange):
    response = drive_api.client.get(
        f"{BASE}/callback",
        params={"code": "code", "state": "forged"},
        follow_redirects=False,
    )
    assert response.headers["location"].endswith("google_drive=error")
    status = drive_api.client.get(f"{BASE}/status", headers=drive_api.headers(1))
    assert status.json()["data"]["connected"] is False


def test_callback_success_redirects_to_processos_and_status_connected(
    drive_api, exchange
):
    connect(drive_api)
    status = drive_api.client.get(f"{BASE}/status", headers=drive_api.headers(2))
    assert status.json()["data"] == {
        "connected": True,
        "email": "escritorio@example.test",
    }


def test_disconnect_then_status_disconnected(drive_api, exchange, monkeypatch):
    from app.modules.google_drive import service

    monkeypatch.setattr(service, "revoke_refresh_token", lambda token: None)
    connect(drive_api)
    response = drive_api.client.delete(BASE, headers=drive_api.headers(1))
    assert response.status_code == 204
    status = drive_api.client.get(f"{BASE}/status", headers=drive_api.headers(1))
    assert status.json()["data"]["connected"] is False


def test_oauth_state_is_not_accepted_as_login_token(drive_api):
    auth_url = drive_api.client.get(
        f"{BASE}/auth-url", headers=drive_api.headers(1)
    ).json()["data"]["auth_url"]
    state = parse_qs(urlparse(auth_url).query)["state"][0]

    response = drive_api.client.get(
        f"{BASE}/status", headers={"Authorization": f"Bearer {state}"}
    )

    assert response.status_code == 401
