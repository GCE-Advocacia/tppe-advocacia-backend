import pytest

THEMES_URL = "/api/v1/office-config/themes"
OFFICE_CONFIG_URL = "/api/v1/office-config"


def valid_theme_payload(name="Tema Customizado Teste"):
    return {
        "name": name,
        "description": "Uma bela descrição",
        "color": "#112233",
        "color_bg_primary": "#112233",
        "color_bg_secondary": "#f4f4f4",
        "color_bg_sobre": "#ffffff",
        "color_buttons": "#c5a059",
        "color_buttons_hover": "#a38038",
        "color_buttons_text": "#ffffff",
        "color_title_primary": "#ffffff",
        "color_title_secondary": "#112233",
        "color_text_primary": "#ffffff",
        "color_text_secondary": "#555555",
        "color_link_primary": "#ffffff",
        "color_link_secondary": "#c5a059",
    }


class TestListThemesE2E:
    def test_returns_at_least_3_predefined_themes(self, client):
        response = client.get(THEMES_URL)
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 3
        predefined = [t for t in data if t["is_predefined"]]
        assert len(predefined) >= 3
        assert any(t["name"] == "Clássico Navy & Wine (Padrão)" for t in predefined)


class TestCreateThemeE2E:
    def test_non_admin_cannot_create_theme(self, client, user_headers):
        response = client.post(
            THEMES_URL,
            json=valid_theme_payload(),
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_admin_can_create_theme(self, client, admin_headers):
        payload = valid_theme_payload("Tema Admin E2E")
        response = client.post(
            THEMES_URL,
            json=payload,
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Tema Admin E2E"
        assert data["is_predefined"] is False
        assert data["color"] == "#112233"

        # Cleanup
        theme_id = data["id"]
        client.delete(f"{THEMES_URL}/{theme_id}", headers=admin_headers)


class TestUpdateAndDeleteThemeE2E:
    def test_admin_can_update_theme(self, client, admin_headers):
        # Create theme first
        res = client.post(
            THEMES_URL,
            json=valid_theme_payload("Tema Para Atualizar"),
            headers=admin_headers,
        )
        theme_id = res.json()["data"]["id"]

        update_res = client.put(
            f"{THEMES_URL}/{theme_id}",
            json={"name": "Tema Atualizado com Sucesso", "color_buttons": "#990000"},
            headers=admin_headers,
        )
        assert update_res.status_code == 200
        data = update_res.json()["data"]
        assert data["name"] == "Tema Atualizado com Sucesso"
        assert data["color_buttons"] == "#990000"

        # Cleanup
        client.delete(f"{THEMES_URL}/{theme_id}", headers=admin_headers)

    def test_admin_cannot_delete_predefined_theme(self, client, admin_headers):
        res = client.get(THEMES_URL)
        themes = res.json()["data"]
        predef = next(t for t in themes if t["is_predefined"])

        del_res = client.delete(
            f"{THEMES_URL}/{predef['id']}",
            headers=admin_headers,
        )
        assert del_res.status_code == 400
        assert del_res.json()["error"]["code"] == "PREDEFINED_THEME_DELETE_NOT_ALLOWED"

    def test_admin_can_delete_custom_theme(self, client, admin_headers):
        res = client.post(
            THEMES_URL,
            json=valid_theme_payload("Tema Para Deletar"),
            headers=admin_headers,
        )
        theme_id = res.json()["data"]["id"]

        del_res = client.delete(f"{THEMES_URL}/{theme_id}", headers=admin_headers)
        assert del_res.status_code == 204

        # Verify it no longer exists
        get_res = client.get(THEMES_URL)
        assert all(t["id"] != theme_id for t in get_res.json()["data"])


class TestThemeQuotaE2E:
    def test_get_theme_quota_returns_dynamic_limits_and_counts(self, client):
        response = client.get(f"{THEMES_URL}/quota")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "max_total" in data
        assert "max_custom" in data
        assert "total_count" in data
        assert "custom_count" in data
        assert "is_limit_reached" in data
        assert data["max_total"] == 9
        assert data["max_custom"] == 6
        assert data["total_count"] >= 3


class TestApplyThemeE2E:
    def test_non_admin_cannot_apply_theme(self, client, user_headers):
        res = client.get(THEMES_URL)
        theme_id = res.json()["data"][0]["id"]

        apply_res = client.post(
            f"{THEMES_URL}/{theme_id}/apply",
            headers=user_headers,
        )
        assert apply_res.status_code == 403

    def test_admin_can_apply_theme(self, client, admin_headers):
        res = client.get(THEMES_URL)
        themes = res.json()["data"]
        # Find the Dourado & Ônix theme
        target_theme = next(
            (t for t in themes if "Dourado" in t["name"]),
            themes[0],
        )

        apply_res = client.post(
            f"{THEMES_URL}/{target_theme['id']}/apply",
            headers=admin_headers,
        )
        assert apply_res.status_code == 200
        config_data = apply_res.json()["data"]
        assert config_data["theme_id"] == target_theme["id"]
        assert config_data["color_buttons"] == target_theme["color_buttons"]
        assert config_data["color_bg_primary"] == target_theme["color_bg_primary"]

        # Check that GET /office-config returns the applied colors and theme_id
        cfg_res = client.get(OFFICE_CONFIG_URL)
        assert cfg_res.status_code == 200
        assert cfg_res.json()["data"]["theme_id"] == target_theme["id"]
        assert cfg_res.json()["data"]["color_buttons"] == target_theme["color_buttons"]
