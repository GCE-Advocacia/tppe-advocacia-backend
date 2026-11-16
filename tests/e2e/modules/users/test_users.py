USERS_URL = "/api/v1/users"


class TestListUsers:
    def test_returns_200(self, client, admin_headers):
        response = client.get(USERS_URL, headers=admin_headers)

        assert response.status_code == 200

    def test_returns_401_without_token(self, client):
        response = client.get(USERS_URL)

        assert response.status_code == 401

    def test_selector_is_available_to_user_with_tasks_or_processes(
        self, client, user_headers
    ):
        response = client.get(USERS_URL, headers=user_headers)

        assert response.status_code == 200

    def test_success_is_true(self, client, admin_headers):
        response = client.get(USERS_URL, headers=admin_headers)

        assert response.json()["success"] is True

    def test_returns_paginated_structure(self, client, admin_headers):
        response = client.get(USERS_URL, headers=admin_headers)
        meta = response.json()["meta"]

        assert "total" in meta
        assert "page" in meta
        assert "limit" in meta
        assert "pages" in meta

    def test_filters_by_role(self, client, admin_headers, admin_user):
        response = client.get(f"{USERS_URL}?role=ADMIN", headers=admin_headers)

        assert all(u["role"] == "ADMIN" for u in response.json()["data"])

    def test_filters_by_is_active(self, client, admin_headers, active_user):
        response = client.get(f"{USERS_URL}?is_active=true", headers=admin_headers)

        assert all(u["is_active"] is True for u in response.json()["data"])

    def test_pagination_respects_limit(self, client, admin_headers):
        response = client.get(f"{USERS_URL}?limit=1", headers=admin_headers)

        assert len(response.json()["data"]) <= 1

    def test_invalid_limit_returns_422(self, client, admin_headers):
        response = client.get(f"{USERS_URL}?limit=0", headers=admin_headers)

        assert response.status_code == 422


class TestCreateUser:
    def test_returns_201(self, client, admin_headers, created_user_ids):
        response = client.post(
            USERS_URL,
            json={"name": "New User", "email": "e2e_create@test.com"},
            headers=admin_headers,
        )
        if response.status_code == 201:
            created_user_ids.append(response.json()["data"]["id"])

        assert response.status_code == 201

    def test_returns_401_without_token(self, client):
        response = client.post(USERS_URL, json={"name": "X", "email": "x@test.com"})

        assert response.status_code == 401

    def test_returns_403_with_user_token(self, client, user_headers):
        response = client.post(
            USERS_URL, json={"name": "X", "email": "x@test.com"}, headers=user_headers
        )

        assert response.status_code == 403

    def test_returns_user_data(self, client, admin_headers, created_user_ids):
        response = client.post(
            USERS_URL,
            json={"name": "Alice", "email": "e2e_alice@test.com"},
            headers=admin_headers,
        )
        created_user_ids.append(response.json()["data"]["id"])
        data = response.json()["data"]

        assert data["name"] == "Alice"
        assert data["email"] == "e2e_alice@test.com"
        assert data["role"] == "USER"
        assert data["is_active"] is True
        assert "id" in data

    def test_duplicate_email_returns_409(self, client, admin_headers, active_user):
        response = client.post(
            USERS_URL,
            json={"name": "Duplicate", "email": active_user["email"]},
            headers=admin_headers,
        )

        assert response.status_code == 409

    def test_duplicate_email_returns_error_code(
        self, client, admin_headers, active_user
    ):
        response = client.post(
            USERS_URL,
            json={"name": "Duplicate", "email": active_user["email"]},
            headers=admin_headers,
        )

        assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    def test_missing_name_returns_422(self, client, admin_headers):
        response = client.post(
            USERS_URL, json={"email": "noname@test.com"}, headers=admin_headers
        )

        assert response.status_code == 422

    def test_missing_email_returns_422(self, client, admin_headers):
        response = client.post(
            USERS_URL, json={"name": "No Email"}, headers=admin_headers
        )

        assert response.status_code == 422

    def test_invalid_email_format_returns_422(self, client, admin_headers):
        response = client.post(
            USERS_URL,
            json={"name": "Bad Email", "email": "not-an-email"},
            headers=admin_headers,
        )

        assert response.status_code == 422


class TestGetUser:
    def test_returns_200_when_found(self, client, admin_headers, active_user):
        response = client.get(f"{USERS_URL}/{active_user['id']}", headers=admin_headers)

        assert response.status_code == 200

    def test_returns_401_without_token(self, client, active_user):
        response = client.get(f"{USERS_URL}/{active_user['id']}")

        assert response.status_code == 401

    def test_returns_403_with_user_token(self, client, user_headers, active_user):
        response = client.get(f"{USERS_URL}/{active_user['id']}", headers=user_headers)

        assert response.status_code == 403

    def test_returns_user_data(self, client, admin_headers, active_user):
        response = client.get(f"{USERS_URL}/{active_user['id']}", headers=admin_headers)
        data = response.json()["data"]

        assert data["id"] == active_user["id"]
        assert data["email"] == active_user["email"]

    def test_returns_404_when_not_found(self, client, admin_headers):
        response = client.get(f"{USERS_URL}/999999", headers=admin_headers)

        assert response.status_code == 404

    def test_returns_error_code_when_not_found(self, client, admin_headers):
        response = client.get(f"{USERS_URL}/999999", headers=admin_headers)

        assert response.json()["error"]["code"] == "USER_NOT_FOUND"


class TestUpdateUser:
    def test_returns_200_on_success(self, client, admin_headers, active_user):
        response = client.patch(
            f"{USERS_URL}/{active_user['id']}",
            json={"name": "Updated Name"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_returns_401_without_token(self, client, active_user):
        response = client.patch(f"{USERS_URL}/{active_user['id']}", json={"name": "X"})

        assert response.status_code == 401

    def test_returns_403_with_user_token(self, client, user_headers, active_user):
        response = client.patch(
            f"{USERS_URL}/{active_user['id']}",
            json={"name": "X"},
            headers=user_headers,
        )

        assert response.status_code == 403

    def test_returns_404_when_not_found(self, client, admin_headers):
        response = client.patch(
            f"{USERS_URL}/999999", json={"name": "X"}, headers=admin_headers
        )

        assert response.status_code == 404

    def test_updates_name(self, client, admin_headers, active_user):
        response = client.patch(
            f"{USERS_URL}/{active_user['id']}",
            json={"name": "New Name"},
            headers=admin_headers,
        )

        assert response.json()["data"]["name"] == "New Name"

    def test_updates_role_to_admin(self, client, admin_headers, active_user):
        response = client.patch(
            f"{USERS_URL}/{active_user['id']}",
            json={"role": "ADMIN"},
            headers=admin_headers,
        )

        assert response.json()["data"]["role"] == "ADMIN"

    def test_deactivates_user(self, client, admin_headers, active_user):
        response = client.patch(
            f"{USERS_URL}/{active_user['id']}",
            json={"is_active": False},
            headers=admin_headers,
        )

        assert response.json()["data"]["is_active"] is False

    def test_duplicate_email_returns_409(
        self, client, admin_headers, active_user, inactive_user
    ):
        response = client.patch(
            f"{USERS_URL}/{active_user['id']}",
            json={"email": inactive_user["email"]},
            headers=admin_headers,
        )

        assert response.status_code == 409

    def test_invalid_email_format_returns_422(self, client, admin_headers, active_user):
        response = client.patch(
            f"{USERS_URL}/{active_user['id']}",
            json={"email": "not-an-email"},
            headers=admin_headers,
        )

        assert response.status_code == 422
