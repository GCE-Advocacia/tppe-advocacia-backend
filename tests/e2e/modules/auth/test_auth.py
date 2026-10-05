import re

import jwt

from app.config.settings import get_settings

LOGIN_URL = "/api/v1/auth/login"
REQUEST_URL = "/api/v1/auth/password-reset/request"
CONFIRM_URL = "/api/v1/auth/password-reset/confirm"


def _extract_token(html: str) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", html)
    assert match, f"Token not found in email html: {html}"
    return match.group(1)


class TestLogin:
    def test_returns_200(self, client, active_user):
        response = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": active_user["password"]},
        )

        assert response.status_code == 200

    def test_success_is_true(self, client, active_user):
        response = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": active_user["password"]},
        )

        assert response.json()["success"] is True

    def test_returns_access_token(self, client, active_user):
        response = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": active_user["password"]},
        )

        assert "access_token" in response.json()["data"]
        assert len(response.json()["data"]["access_token"]) > 0

    def test_token_type_is_bearer(self, client, active_user):
        response = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": active_user["password"]},
        )

        assert response.json()["data"]["token_type"] == "bearer"

    def test_token_contains_can_view_payments_false_for_new_user(
        self, client, active_user
    ):
        response = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": active_user["password"]},
        )

        token = response.json()["data"]["access_token"]
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        assert payload["can_view_payments"] is False

    def test_wrong_password_returns_401(self, client, active_user):
        response = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": "wrong_password"},
        )

        assert response.status_code == 401

    def test_wrong_password_returns_error_code(self, client, active_user):
        response = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": "wrong_password"},
        )

        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_unknown_email_returns_401(self, client):
        response = client.post(
            LOGIN_URL, json={"email": "nobody@test.com", "password": "any_password"}
        )

        assert response.status_code == 401

    def test_unknown_email_same_error_as_wrong_password(self, client, active_user):
        wrong_pass = client.post(
            LOGIN_URL, json={"email": active_user["email"], "password": "wrong"}
        )
        unknown = client.post(
            LOGIN_URL, json={"email": "nobody@test.com", "password": "wrong"}
        )

        assert wrong_pass.json()["error"]["code"] == unknown.json()["error"]["code"]

    def test_inactive_user_returns_403(self, client, inactive_user):
        response = client.post(
            LOGIN_URL,
            json={
                "email": inactive_user["email"],
                "password": inactive_user["password"],
            },
        )

        assert response.status_code == 403

    def test_inactive_user_returns_error_code(self, client, inactive_user):
        response = client.post(
            LOGIN_URL,
            json={
                "email": inactive_user["email"],
                "password": inactive_user["password"],
            },
        )

        assert response.json()["error"]["code"] == "INACTIVE_USER"

    def test_missing_email_returns_422(self, client):
        response = client.post(LOGIN_URL, json={"password": "any_password"})

        assert response.status_code == 422

    def test_missing_password_returns_422(self, client):
        response = client.post(LOGIN_URL, json={"email": "user@test.com"})

        assert response.status_code == 422

    def test_invalid_email_format_returns_422(self, client):
        response = client.post(
            LOGIN_URL, json={"email": "not-an-email", "password": "any_password"}
        )

        assert response.status_code == 422

    def test_empty_body_returns_422(self, client):
        response = client.post(LOGIN_URL, json={})

        assert response.status_code == 422


class TestRequestPasswordReset:
    def test_returns_200_for_existing_active_user(
        self, client, active_user, fake_email
    ):
        response = client.post(REQUEST_URL, json={"email": active_user["email"]})

        assert response.status_code == 200

    def test_success_is_true_for_existing_active_user(
        self, client, active_user, fake_email
    ):
        response = client.post(REQUEST_URL, json={"email": active_user["email"]})

        assert response.json()["success"] is True

    def test_sends_email_to_active_user(self, client, active_user, fake_email):
        client.post(REQUEST_URL, json={"email": active_user["email"]})

        assert len(fake_email.sent) == 1
        assert fake_email.sent[0]["to"] == active_user["email"]

    def test_returns_200_for_unknown_email(self, client, fake_email):
        response = client.post(REQUEST_URL, json={"email": "nobody@test.com"})

        assert response.status_code == 200

    def test_does_not_send_email_for_unknown_email(self, client, fake_email):
        client.post(REQUEST_URL, json={"email": "nobody@test.com"})

        assert len(fake_email.sent) == 0

    def test_returns_200_for_inactive_user(self, client, inactive_user, fake_email):
        response = client.post(REQUEST_URL, json={"email": inactive_user["email"]})

        assert response.status_code == 200

    def test_does_not_send_email_for_inactive_user(
        self, client, inactive_user, fake_email
    ):
        client.post(REQUEST_URL, json={"email": inactive_user["email"]})

        assert len(fake_email.sent) == 0

    def test_missing_email_returns_422(self, client, fake_email):
        response = client.post(REQUEST_URL, json={})

        assert response.status_code == 422

    def test_invalid_email_format_returns_422(self, client, fake_email):
        response = client.post(REQUEST_URL, json={"email": "not-an-email"})

        assert response.status_code == 422


class TestConfirmPasswordReset:
    def test_full_flow_allows_login_with_new_password(
        self, client, active_user, fake_email
    ):
        client.post(REQUEST_URL, json={"email": active_user["email"]})
        token = _extract_token(fake_email.sent[0]["html"])

        confirm = client.post(
            CONFIRM_URL, json={"token": token, "new_password": "NewPass@123"}
        )
        assert confirm.status_code == 200

        login = client.post(
            LOGIN_URL, json={"email": active_user["email"], "password": "NewPass@123"}
        )
        assert login.status_code == 200

    def test_old_password_does_not_work_after_reset(
        self, client, active_user, fake_email
    ):
        client.post(REQUEST_URL, json={"email": active_user["email"]})
        token = _extract_token(fake_email.sent[0]["html"])
        client.post(CONFIRM_URL, json={"token": token, "new_password": "NewPass@123"})

        login = client.post(
            LOGIN_URL,
            json={"email": active_user["email"], "password": active_user["password"]},
        )
        assert login.status_code == 401

    def test_invalid_token_returns_400(self, client, fake_email):
        response = client.post(
            CONFIRM_URL, json={"token": "invalidtoken", "new_password": "NewPass@123"}
        )

        assert response.status_code == 400

    def test_invalid_token_returns_correct_code(self, client, fake_email):
        response = client.post(
            CONFIRM_URL, json={"token": "invalidtoken", "new_password": "NewPass@123"}
        )

        assert response.json()["error"]["code"] == "INVALID_RESET_TOKEN"

    def test_token_used_twice_returns_400(self, client, active_user, fake_email):
        client.post(REQUEST_URL, json={"email": active_user["email"]})
        token = _extract_token(fake_email.sent[0]["html"])
        client.post(CONFIRM_URL, json={"token": token, "new_password": "NewPass@123"})

        response = client.post(
            CONFIRM_URL, json={"token": token, "new_password": "AnotherPass@1"}
        )
        assert response.status_code == 400

    def test_short_password_returns_422(self, client, active_user, fake_email):
        client.post(REQUEST_URL, json={"email": active_user["email"]})
        token = _extract_token(fake_email.sent[0]["html"])

        response = client.post(
            CONFIRM_URL, json={"token": token, "new_password": "short"}
        )
        assert response.status_code == 422

    def test_missing_token_returns_422(self, client, fake_email):
        response = client.post(CONFIRM_URL, json={"new_password": "NewPass@123"})

        assert response.status_code == 422

    def test_missing_new_password_returns_422(self, client, fake_email):
        response = client.post(CONFIRM_URL, json={"token": "sometoken"})

        assert response.status_code == 422
